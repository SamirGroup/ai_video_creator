"""Celery tasks for the video generation pipeline (SPEC 7.1, FR-42..FR-45, FR-52).

Each stage:
- runs on its own queue (`q_script`, `q_voice`, `q_visual`, `q_render`, `q_upload`)
  so it can be scaled/rate-limited independently (see docker-compose.yml);
- is idempotent — the idempotency key is `(job_id, stage, attempt)`, recorded
  as a `VideoJobStep` row before any provider call, so an at-least-once retry
  never double-charges or double-uploads (NFR-25);
- retries 3 times with the FR-44 backoff ladder (30s / 2min / 8min) before moving
  the job to `failed`;
- uses `acks_late=True` so a worker crash mid-task re-queues the job instead
  of silently dropping it.

IMPLEMENTATION STATUS
---------------------
* `generate_script`  — implemented (OpenRouter/Claude via `services.script_generation`).
* `moderate_content` — implemented for `scope="script"` (OpenAI Moderation, FR-45).
  `scope="visual"/"final"` (FR-46, AWS Rekognition) is still a stub.
* `generate_voice`, `generate_visuals`, `assemble_video`, `upload_to_youtube`
  — still stubs. The pipeline therefore stops after script moderation.

Error handling contract (see `providers.exceptions`): a `ProviderRetryableError`
triggers `self.retry`; any other `ProviderError` fails the job immediately, because
retrying a deterministic 400/auth/config error only burns money and rate limit.
"""
from __future__ import annotations

import logging
import random

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError, Retry
from django.utils import timezone

from moderation.models import ModerationStage
from providers.exceptions import ProviderError, ProviderRetryableError
from providers.models import ServiceType
from providers.services import get_primary_config, operation_cost_usd
from video_pipeline.models import JobStatus, Stage, StepStatus, VideoJob, VideoJobStep

logger = logging.getLogger("video_pipeline.tasks")

RETRY_BACKOFF_SECONDS = 30  # first retry delay; see RETRY_COUNTDOWNS for the full ladder
MAX_RETRIES = 3
# FR-44: "3 urinish, eksponensial backoff (30s/2min/8min)". Celery's `retry_backoff`
# option only applies to `autoretry_for`; these tasks retry manually, so the ladder
# is applied explicitly via `countdown=`.
RETRY_COUNTDOWNS = (30, 120, 480)


def _retry_countdown(retries: int) -> int:
    """Backoff for the upcoming attempt, with +-10% jitter so a provider outage
    doesn't produce a synchronised retry stampede (NFR-24).
    """
    base = RETRY_COUNTDOWNS[min(retries, len(RETRY_COUNTDOWNS) - 1)]
    return max(1, int(base * random.uniform(0.9, 1.1)))


def _record_step_started(job_id: str, stage: str, attempt: int, provider: str) -> VideoJobStep:
    return VideoJobStep.objects.create(
        job_id=job_id,
        stage=stage,
        attempt=attempt,
        status=StepStatus.STARTED,
        provider=provider,
        started_at=timezone.now(),
    )


def _record_step_result(
    step: VideoJobStep,
    *,
    status: str,
    error_code: str = "",
    error_detail: str = "",
    cost_usd=0,
    output_ref: str = "",
    provider_request_id: str = "",
) -> VideoJobStep:
    # VideoJobStep is append-only (core.models.AppendOnlyModel) — the "result" is
    # always a NEW row, never an update of `step`, to preserve full attempt history.
    finished_at = timezone.now()
    duration_ms = int((finished_at - step.started_at).total_seconds() * 1000)
    return VideoJobStep.objects.create(
        job_id=step.job_id,
        stage=step.stage,
        attempt=step.attempt,
        status=status,
        provider=step.provider,
        provider_request_id=provider_request_id[:128],
        started_at=step.started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        cost_usd=cost_usd or 0,
        error_code=error_code[:64],
        error_detail=error_detail,
        output_ref=output_ref,
    )


class StageNotImplemented(Exception):
    """Raised by stub stages so Celery logs a clean, expected failure instead
    of an AttributeError from a missing provider client.
    """


# ---------------------------------------------------------------------------
# Shared job-state helpers
# ---------------------------------------------------------------------------
def _load_job(job_id: str) -> VideoJob | None:
    return VideoJob.objects.select_related("preference", "user", "channel").filter(pk=job_id).first()


def _provider_label(service: str, default: str = "") -> str:
    """Best-effort provider name for the step row; never blocks the stage."""
    try:
        return get_primary_config(service).provider
    except Exception:
        return default


def _set_status(job: VideoJob, status: str, stage: str | None = None, *, mark_started: bool = False) -> None:
    job.status = status
    fields = ["status", "updated_at"]
    if stage is not None:
        job.current_stage = stage
        fields.append("current_stage")
    if mark_started and job.started_at is None:
        job.started_at = timezone.now()
        fields.append("started_at")
    job.save(update_fields=fields)


def _fail_job(job: VideoJob, error_code: str, message: str) -> None:
    """Terminal failure for a stage (FR-44).

    NOTE for the billing/notification owners: quota refund (`usage_counters`,
    "kvota qaytariladi" in SPEC 7.2), the admin alert and the creator
    notification hang off this transition. They are intentionally not written
    here — `billing` and `notifications` are owned by other stages of the build.
    """
    job.status = JobStatus.FAILED
    job.error_code = (error_code or "stage_failed")[:64]
    job.error_message = message
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "error_code", "error_message", "completed_at", "updated_at"])
    logger.error(
        "pipeline_stage_failed_terminal",
        extra={"job_id": str(job.pk), "error_code": job.error_code, "stage": job.current_stage},
    )


def _should_skip(job: VideoJob) -> bool:
    """Do not resurrect a job a creator/admin already cancelled or that finished."""
    return job.is_terminal()


# ---------------------------------------------------------------------------
# Stage 1 — script generation (implemented)
# ---------------------------------------------------------------------------
@shared_task(
    bind=True,
    queue="q_script",
    max_retries=MAX_RETRIES,
    retry_backoff=RETRY_BACKOFF_SECONDS,
    retry_backoff_max=8 * 60,
    retry_jitter=True,
    acks_late=True,
)
def generate_script(self, job_id: str, chain_next: bool = True):
    """Stage 1 (SPEC 7.1 #1): niche/brief/brand_voice + last-20 topics ->
    title / description / tags / segmented script (FR-33, FR-34, FR-37).

    Provider: OpenRouter (Claude), selected from `api_credentials_config`.
    On success the job reaches `script_ready` and, unless `chain_next=False`,
    the FR-45 script moderation gate is queued immediately.
    """
    from video_pipeline.services.script_generation import (
        OPERATION,
        generate_script_for_job,
    )

    attempt = self.request.retries + 1
    job = _load_job(job_id)
    if job is None:
        logger.warning("script_stage_job_missing", extra={"job_id": str(job_id)})
        return {"job_id": str(job_id), "status": "missing"}
    if _should_skip(job):
        logger.info("script_stage_skipped_terminal", extra={"job_id": str(job_id), "status": job.status})
        return {"job_id": str(job_id), "status": job.status, "skipped": True}

    step = _record_step_started(
        job_id, Stage.SCRIPT, attempt, provider=_provider_label(ServiceType.LLM, "openrouter")
    )
    _set_status(job, JobStatus.GENERATING_SCRIPT, Stage.SCRIPT, mark_started=True)

    try:
        script = generate_script_for_job(job, attempt=attempt)
    except ProviderRetryableError as exc:
        _record_step_result(
            step,
            status=StepStatus.FAILED,
            error_code=exc.error_code,
            error_detail=str(exc),
            cost_usd=operation_cost_usd(job.pk, OPERATION),
        )
        return _retry_or_fail(self, job, exc)
    except ProviderError as exc:
        _record_step_result(
            step,
            status=StepStatus.FAILED,
            error_code=exc.error_code,
            error_detail=str(exc),
            cost_usd=operation_cost_usd(job.pk, OPERATION),
        )
        _fail_job(job, exc.error_code, str(exc))
        raise
    except Exception as exc:  # unexpected — record, fail loudly, do not retry blindly
        _record_step_result(
            step, status=StepStatus.FAILED, error_code="internal_error", error_detail=str(exc)
        )
        _fail_job(job, "internal_error", str(exc))
        raise

    _record_step_result(
        step,
        status=StepStatus.SUCCEEDED,
        cost_usd=operation_cost_usd(job.pk, OPERATION),
        output_ref=f"video_jobs.{job.pk}.script_text",
        provider_request_id=str(script.meta.get("provider_request_id") or ""),
    )
    _set_status(job, JobStatus.SCRIPT_READY, Stage.SCRIPT)

    logger.info(
        "script_stage_succeeded",
        extra={
            "job_id": str(job.pk),
            "segments": len(script.segments),
            "words": script.word_count,
            "estimated_duration_sec": script.estimated_duration_sec,
        },
    )

    if chain_next:
        moderate_content.apply_async(
            args=[str(job.pk)], kwargs={"scope": ModerationStage.SCRIPT}
        )

    return {
        "job_id": str(job.pk),
        "status": job.status,
        "title": script.title,
        "segments": len(script.segments),
        "estimated_duration_sec": script.estimated_duration_sec,
    }


def _retry_or_fail(task, job: VideoJob, exc: ProviderRetryableError):
    """Shared retry path: `retrying` status, FR-44 backoff, terminal `failed`
    once the retry budget is spent.
    """
    countdown = getattr(exc, "retry_after_sec", None) or _retry_countdown(task.request.retries)

    job.retry_count = (job.retry_count or 0) + 1
    job.status = JobStatus.RETRYING
    job.error_code = exc.error_code[:64]
    job.error_message = str(exc)
    job.save(update_fields=["retry_count", "status", "error_code", "error_message", "updated_at"])

    try:
        raise task.retry(exc=exc, countdown=countdown)
    except Retry:
        raise
    except MaxRetriesExceededError:
        _fail_job(job, exc.error_code, f"Retries exhausted after {MAX_RETRIES} attempts: {exc}")
        raise


# ---------------------------------------------------------------------------
# Stage 2 & 6 — moderation (script implemented, visual/final still stubbed)
# ---------------------------------------------------------------------------
@shared_task(
    bind=True,
    queue="celery",
    max_retries=MAX_RETRIES,
    retry_backoff=RETRY_BACKOFF_SECONDS,
    retry_backoff_max=8 * 60,
    retry_jitter=True,
    acks_late=True,
)
def moderate_content(self, job_id: str, scope: str = ModerationStage.SCRIPT, chain_next: bool = True):
    """Stages 2 & 6 (SPEC 7.1 #2, #6): moderation gate (FR-45, FR-46, FR-48).

    `scope="script"`: OpenAI Moderation over `job.script_text`, one
    `moderation_logs` row per run, verdict mapped onto `video_jobs.status`; a
    pass chains straight into stage 3 (voice). `scope="final"`: AWS
    Rekognition over the assembled video's keyframes (FR-46) — a pass hands
    off to `video_pipeline.services.approval.on_final_moderation_passed`
    (review_required -> `awaiting_approval`, auto -> upload). `scope="audio"`
    / `"visual"` are not part of SPEC 7.1's pipeline (final moderation reuses
    the script-stage verdict for audio) and remain stubs.

    A flagged or blocked script/video goes to `moderation_review` — the human
    moderator queue — never to auto-publish (FR-48).
    """
    attempt = self.request.retries + 1
    job = _load_job(job_id)
    if job is None:
        logger.warning("moderation_stage_job_missing", extra={"job_id": str(job_id)})
        return {"job_id": str(job_id), "status": "missing"}
    if _should_skip(job):
        logger.info("moderation_stage_skipped_terminal", extra={"job_id": str(job_id)})
        return {"job_id": str(job_id), "status": job.status, "skipped": True}

    if scope == ModerationStage.FINAL:
        return _moderate_final(self, job, attempt)

    if scope != ModerationStage.SCRIPT:
        step = _record_step_started(job_id, Stage.MODERATION, attempt, provider="aws_rekognition")
        try:
            raise StageNotImplemented(f"Moderation scope '{scope}' is not wired yet.")
        except StageNotImplemented as exc:
            _record_step_result(
                step, status=StepStatus.FAILED, error_code="not_implemented", error_detail=str(exc)
            )
            raise self.retry(exc=exc, countdown=_retry_countdown(self.request.retries))

    from video_pipeline.services.script_moderation import (
        OPERATION,
        apply_verdict_to_job,
        moderate_script_for_job,
    )

    step = _record_step_started(
        job_id, Stage.MODERATION, attempt, provider=_provider_label(ServiceType.MODERATION, "openai_moderation")
    )
    _set_status(job, JobStatus.MODERATING_SCRIPT, Stage.MODERATION)

    try:
        outcome = moderate_script_for_job(job)
    except ProviderRetryableError as exc:
        _record_step_result(
            step, status=StepStatus.FAILED, error_code=exc.error_code, error_detail=str(exc)
        )
        return _retry_or_fail(self, job, exc)
    except ProviderError as exc:
        _record_step_result(
            step, status=StepStatus.FAILED, error_code=exc.error_code, error_detail=str(exc)
        )
        _fail_job(job, exc.error_code, str(exc))
        raise
    except Exception as exc:
        _record_step_result(
            step, status=StepStatus.FAILED, error_code="internal_error", error_detail=str(exc)
        )
        _fail_job(job, "internal_error", str(exc))
        raise

    _record_step_result(
        step,
        status=StepStatus.SUCCEEDED,
        cost_usd=operation_cost_usd(job.pk, OPERATION),
        output_ref=f"moderation_logs.job={job.pk}.stage=script",
        provider_request_id=str((outcome.raw_response or {}).get("id") or ""),
    )

    new_status = apply_verdict_to_job(job, outcome)

    if outcome.is_blocking:
        # FR-48: stops here on purpose. A moderator decides via
        # POST /api/v1/admin/moderation/{job_id}/decide.
        logger.warning(
            "script_moderation_blocked",
            extra={
                "job_id": str(job.pk),
                "verdict": outcome.verdict,
                "category": outcome.max_category,
                "status": new_status,
            },
        )
    else:
        logger.info("script_moderation_passed", extra={"job_id": str(job.pk), "next_stage": "voice"})
        if chain_next:
            generate_voice.apply_async(args=[str(job.pk)])

    return {
        "job_id": str(job.pk),
        "status": new_status,
        "verdict": outcome.verdict,
        "max_category": outcome.max_category,
        "max_score": outcome.max_score,
    }


def _moderate_final(task, job: VideoJob, attempt: int) -> dict:
    """Stage 6 (SPEC 7.1 #6): AWS Rekognition over the assembled video's
    keyframes (FR-46). Split out from `moderate_content` because it shares
    almost none of the script branch's imports/logic.
    """
    from video_pipeline.services.visual_moderation import (
        OPERATION,
        apply_final_verdict_to_job,
        moderate_final_video_for_job,
    )

    job_id = str(job.pk)
    step = _record_step_started(
        job_id, Stage.MODERATION, attempt, provider=_provider_label(ServiceType.MODERATION, "aws_rekognition")
    )
    _set_status(job, JobStatus.MODERATING_FINAL, Stage.MODERATION)

    try:
        outcome = moderate_final_video_for_job(job)
    except ProviderRetryableError as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.error_code, error_detail=str(exc))
        return _retry_or_fail(task, job, exc)
    except ProviderError as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.error_code, error_detail=str(exc))
        _fail_job(job, exc.error_code, str(exc))
        raise
    except Exception as exc:  # noqa: BLE001 — unexpected, fail loudly, do not retry blindly
        _record_step_result(step, status=StepStatus.FAILED, error_code="internal_error", error_detail=str(exc))
        _fail_job(job, "internal_error", str(exc))
        raise

    _record_step_result(
        step,
        status=StepStatus.SUCCEEDED,
        cost_usd=operation_cost_usd(job.pk, OPERATION),
        output_ref=f"moderation_logs.job={job.pk}.stage=final",
    )
    new_status = apply_final_verdict_to_job(job, outcome)
    logger.info(
        "final_moderation_stage_completed",
        extra={"job_id": job_id, "verdict": outcome.verdict, "status": new_status},
    )
    return {
        "job_id": job_id,
        "status": new_status,
        "verdict": outcome.verdict,
        "max_category": outcome.max_category,
        "max_score": outcome.max_score,
    }


# ---------------------------------------------------------------------------
# Stage 3 — voice-over (implemented; see video_pipeline.services.voice_generation)
# ---------------------------------------------------------------------------
@shared_task(
    bind=True,
    queue="q_voice",
    max_retries=MAX_RETRIES,
    retry_backoff=RETRY_BACKOFF_SECONDS,
    retry_backoff_max=8 * 60,
    retry_jitter=True,
    acks_late=True,
)
def generate_voice(self, job_id: str, chain_next: bool = True):
    """Stage 3 (SPEC 7.1 #3): script segments + voice_id -> voice-over audio +
    per-segment timing (FR-42, FR-43). Provider: ElevenLabs (Q3 decision).
    """
    from video_pipeline.services.voice_generation import OPERATION, generate_voice_for_job

    attempt = self.request.retries + 1
    job = _load_job(job_id)
    if job is None:
        logger.warning("voice_stage_job_missing", extra={"job_id": str(job_id)})
        return {"job_id": str(job_id), "status": "missing"}
    if _should_skip(job):
        logger.info("voice_stage_skipped_terminal", extra={"job_id": str(job_id), "status": job.status})
        return {"job_id": str(job_id), "status": job.status, "skipped": True}

    step = _record_step_started(
        job_id, Stage.VOICE, attempt, provider=_provider_label(ServiceType.TTS, "elevenlabs")
    )
    _set_status(job, JobStatus.GENERATING_VOICE, Stage.VOICE, mark_started=True)

    try:
        result = generate_voice_for_job(job)
    except ProviderRetryableError as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.error_code, error_detail=str(exc))
        return _retry_or_fail(self, job, exc)
    except ProviderError as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.error_code, error_detail=str(exc))
        _fail_job(job, exc.error_code, str(exc))
        raise
    except Exception as exc:  # noqa: BLE001
        _record_step_result(step, status=StepStatus.FAILED, error_code="internal_error", error_detail=str(exc))
        _fail_job(job, "internal_error", str(exc))
        raise

    _record_step_result(
        step,
        status=StepStatus.SUCCEEDED,
        cost_usd=operation_cost_usd(job.pk, OPERATION),
        output_ref=f"video_assets.job={job.pk}.kind=audio_voice",
    )
    _set_status(job, JobStatus.VOICE_READY, Stage.VOICE)
    logger.info(
        "voice_stage_succeeded",
        extra={
            "job_id": str(job.pk),
            "segments": len(result.segment_timing),
            "duration_ms": result.total_duration_ms,
        },
    )
    if chain_next:
        generate_visuals.apply_async(args=[str(job.pk)])
    return {"job_id": str(job.pk), "status": job.status, "duration_ms": result.total_duration_ms}


# ---------------------------------------------------------------------------
# Stage 4 — visual clips (implemented; see video_pipeline.services.visual_generation)
# ---------------------------------------------------------------------------
@shared_task(
    bind=True,
    queue="q_visual",
    max_retries=MAX_RETRIES,
    retry_backoff=RETRY_BACKOFF_SECONDS,
    retry_backoff_max=8 * 60,
    retry_jitter=True,
    acks_late=True,
)
def generate_visuals(self, job_id: str, chain_next: bool = True):
    """Stage 4 (SPEC 7.1 #4): segment prompts + timing -> per-segment video
    clips (FR-42, FR-43, FR-51, FR-52). Provider: Runway (Q3 decision).
    """
    from video_pipeline.services.visual_generation import OPERATION, generate_visuals_for_job

    attempt = self.request.retries + 1
    job = _load_job(job_id)
    if job is None:
        logger.warning("visuals_stage_job_missing", extra={"job_id": str(job_id)})
        return {"job_id": str(job_id), "status": "missing"}
    if _should_skip(job):
        logger.info("visuals_stage_skipped_terminal", extra={"job_id": str(job_id), "status": job.status})
        return {"job_id": str(job_id), "status": job.status, "skipped": True}

    step = _record_step_started(
        job_id, Stage.VISUALS, attempt, provider=_provider_label(ServiceType.VIDEO_GEN, "runway")
    )
    _set_status(job, JobStatus.GENERATING_VISUALS, Stage.VISUALS, mark_started=True)

    try:
        result = generate_visuals_for_job(job)
    except ProviderRetryableError as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.error_code, error_detail=str(exc))
        return _retry_or_fail(self, job, exc)
    except ProviderError as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.error_code, error_detail=str(exc))
        _fail_job(job, exc.error_code, str(exc))
        raise
    except Exception as exc:  # noqa: BLE001
        _record_step_result(step, status=StepStatus.FAILED, error_code="internal_error", error_detail=str(exc))
        _fail_job(job, "internal_error", str(exc))
        raise

    _record_step_result(
        step,
        status=StepStatus.SUCCEEDED,
        cost_usd=operation_cost_usd(job.pk, OPERATION),
        output_ref=f"video_assets.job={job.pk}.kind=visual_clip",
    )
    _set_status(job, JobStatus.VISUALS_READY, Stage.VISUALS)
    logger.info(
        "visuals_stage_succeeded",
        extra={"job_id": str(job.pk), "generated": result.generated, "skipped": result.skipped},
    )
    if chain_next:
        assemble_video.apply_async(args=[str(job.pk)])
    return {"job_id": str(job.pk), "status": job.status, "clips": len(result.clips)}


# ---------------------------------------------------------------------------
# Stage 5 — FFmpeg assembly (implemented; see video_pipeline.services.assembler)
# ---------------------------------------------------------------------------
@shared_task(
    bind=True,
    queue="q_render",
    max_retries=MAX_RETRIES,
    retry_backoff=RETRY_BACKOFF_SECONDS,
    retry_backoff_max=8 * 60,
    retry_jitter=True,
    acks_late=True,
)
def assemble_video(self, job_id: str, chain_next: bool = True):
    """Stage 5 (SPEC 7.1 #5): clips + voice + music + intro/outro -> final
    MP4 + thumbnail (FR-47, FR-50, A-4, A-5). CPU-heavy — its own worker pool
    (`q_render`, see docker-compose.yml).
    """
    from video_pipeline.services.assembler import OPERATION, assemble_video_for_job

    attempt = self.request.retries + 1
    job = _load_job(job_id)
    if job is None:
        logger.warning("assembly_stage_job_missing", extra={"job_id": str(job_id)})
        return {"job_id": str(job_id), "status": "missing"}
    if _should_skip(job):
        logger.info("assembly_stage_skipped_terminal", extra={"job_id": str(job_id), "status": job.status})
        return {"job_id": str(job_id), "status": job.status, "skipped": True}

    step = _record_step_started(job_id, Stage.ASSEMBLY, attempt, provider="ffmpeg")
    _set_status(job, JobStatus.ASSEMBLING, Stage.ASSEMBLY, mark_started=True)

    try:
        result = assemble_video_for_job(job)
    except ProviderRetryableError as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.error_code, error_detail=str(exc))
        return _retry_or_fail(self, job, exc)
    except ProviderError as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.error_code, error_detail=str(exc))
        _fail_job(job, exc.error_code, str(exc))
        raise
    except Exception as exc:  # noqa: BLE001
        _record_step_result(step, status=StepStatus.FAILED, error_code="internal_error", error_detail=str(exc))
        _fail_job(job, "internal_error", str(exc))
        raise

    _record_step_result(
        step,
        status=StepStatus.SUCCEEDED,
        cost_usd=operation_cost_usd(job.pk, OPERATION),
        output_ref=f"video_assets.job={job.pk}.kind=final_video",
    )
    _set_status(job, JobStatus.ASSEMBLED, Stage.ASSEMBLY)
    logger.info(
        "assembly_stage_succeeded", extra={"job_id": str(job.pk), "duration_ms": result.duration_ms}
    )
    if chain_next:
        moderate_content.apply_async(args=[str(job.pk)], kwargs={"scope": ModerationStage.FINAL})
    return {"job_id": str(job.pk), "status": job.status, "duration_ms": result.duration_ms}


# ---------------------------------------------------------------------------
# FR-38 timeout sweep (periodic, Celery Beat — see migration 0002)
# ---------------------------------------------------------------------------
@shared_task(name="video_pipeline.expire_stale_approvals")
def expire_stale_approvals() -> dict:
    """A-3: jobs left in `awaiting_approval` past the 48h window either
    auto-publish (`ContentPreference.auto_publish_on_timeout=True`) or expire
    without a quota refund (SPEC 7.2). Business logic lives in
    `video_pipeline.services.approval` so it stays unit-testable without Celery.
    """
    from video_pipeline.services.approval import expire_stale_approvals as _expire

    return _expire()


@shared_task(
    bind=True,
    queue="q_upload",
    max_retries=MAX_RETRIES,
    retry_backoff=RETRY_BACKOFF_SECONDS,
    retry_backoff_max=8 * 60,
    retry_jitter=True,
    acks_late=True,
)
def upload_to_youtube(self, job_id: str):
    """Stage 8 (SPEC 7.1 #8): final MP4 + metadata -> youtube_video_id.

    Statuses: `upload_queued -> uploading -> published` (SPEC 7.2; `published`
    as soon as `videos.insert` succeeds, the FR-59 post-publish check refines
    `youtube_upload_status`). Implemented in
    `video_pipeline.services.youtube_upload` (Track C). FR-57 handling:

    * quotaExceeded  -> job stays `upload_queued`, re-enqueued with
      `eta=next_quota_window()` (AC-6: never `failed`);
    * forbidden / invalid_grant -> channel `disconnected` + creator notified,
      job `failed(channel_disconnected)`;
    * transient errors -> FR-44 ladder via `_retry_or_fail`;
    * deterministic errors -> `failed`.
    """
    from video_pipeline.services.youtube_upload import (
        YouTubeAuthError,
        YouTubeQuotaExceeded,
        YouTubeUploadError,
        upload_job_video,
    )

    attempt = self.request.retries + 1
    job = _load_job(job_id)
    if job is None:
        logger.warning("upload_stage_job_missing", extra={"job_id": str(job_id)})
        return {"job_id": str(job_id), "status": "missing"}
    if _should_skip(job):
        logger.info("upload_stage_skipped_terminal", extra={"job_id": str(job_id), "status": job.status})
        return {"job_id": str(job_id), "status": job.status, "skipped": True}
    if job.youtube_video_id:
        # At-least-once re-delivery after a crash between insert and commit — never upload twice.
        logger.info("upload_stage_skipped_already_uploaded", extra={"job_id": str(job_id)})
        return {"job_id": str(job_id), "status": job.status, "skipped": True, "youtube_video_id": job.youtube_video_id}
    if job.status not in _UPLOAD_ACCEPTED_STATUSES:
        logger.info("upload_stage_skipped_wrong_status", extra={"job_id": str(job_id), "status": job.status})
        return {"job_id": str(job_id), "status": job.status, "skipped": True}

    step = _record_step_started(job_id, Stage.UPLOAD, attempt, provider="youtube_data_api")
    _set_status(job, JobStatus.UPLOADING, Stage.UPLOAD, mark_started=True)

    try:
        result = upload_job_video(job)
    except YouTubeQuotaExceeded as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.code, error_detail=str(exc))
        return _requeue_upload_for_next_quota_window(self, job, exc)
    except YouTubeAuthError as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.code, error_detail=str(exc))
        _handle_channel_auth_failure(job, exc)
        return {"job_id": str(job.pk), "status": job.status, "error_code": job.error_code}
    except YouTubeUploadError as exc:
        _record_step_result(step, status=StepStatus.FAILED, error_code=exc.code, error_detail=str(exc))
        if exc.retryable:
            return _retry_or_fail(self, job, ProviderRetryableError(str(exc), error_code=exc.code))
        _fail_job(job, exc.code, str(exc))
        raise
    except Exception as exc:  # unexpected — record, fail loudly, do not retry blindly
        _record_step_result(step, status=StepStatus.FAILED, error_code="internal_error", error_detail=str(exc))
        _fail_job(job, "internal_error", str(exc))
        raise

    _record_step_result(
        step,
        status=StepStatus.SUCCEEDED,
        output_ref=result.url,
        provider_request_id=result.video_id,
    )
    logger.info(
        "upload_stage_succeeded",
        extra={"job_id": str(job.pk), "youtube_video_id": result.video_id, "chunks": result.chunks},
    )
    return {
        "job_id": str(job.pk),
        "status": job.status,
        "youtube_video_id": result.video_id,
        "youtube_url": result.url,
        "thumbnail_set": result.thumbnail_set,
    }


# ---------------------------------------------------------------------------
# Track C — private helpers for the upload stage (FR-57)
# ---------------------------------------------------------------------------
# `approved` is accepted alongside `upload_queued` so an approval flow that
# enqueues directly from `approved` does not need an extra hop.
_UPLOAD_ACCEPTED_STATUSES = frozenset(
    {JobStatus.UPLOAD_QUEUED, JobStatus.APPROVED, JobStatus.UPLOADING, JobStatus.RETRYING}
)


def _requeue_upload_for_next_quota_window(task, job: VideoJob, exc) -> dict:
    """FR-57/AC-6: the job goes back to `upload_queued` (not `failed`) and the
    task is re-enqueued for the next Pacific-midnight quota reset.

    The ETA is hours away; with a Redis broker the message sits in the
    worker's unacked set and is re-delivered after `visibility_timeout`, so
    duplicates are possible — the stage is idempotent (`youtube_video_id`
    guard + status check above), which makes that harmless.
    """
    job.status = JobStatus.UPLOAD_QUEUED
    job.error_code = "quota_exceeded"
    job.error_message = str(exc)
    job.save(update_fields=["status", "error_code", "error_message", "updated_at"])
    eta = exc.next_window
    task.apply_async(args=[str(job.pk)], eta=eta, queue="q_upload")
    logger.warning(
        "upload_stage_requeued_quota",
        extra={"job_id": str(job.pk), "eta": eta.isoformat()},
    )
    return {"job_id": str(job.pk), "status": job.status, "requeued_at": eta.isoformat()}


def _handle_channel_auth_failure(job: VideoJob, exc) -> None:
    """FR-57: `forbidden` / `invalid_grant` -> channel `disconnected`, scheduling
    paused, creator notified, job `failed(channel_disconnected)`.
    """
    from channels.models import ConnectionStatus
    from channels.services import _mark_channel_disconnected_after_refresh_failure
    from notifications.services import notify

    channel = job.channel
    channel.refresh_from_db(fields=["status"])
    if channel.status == ConnectionStatus.CONNECTED:
        # Marks disconnected, pauses preferences, writes the legacy email row + audit.
        _mark_channel_disconnected_after_refresh_failure(channel, error_code=exc.code)
    try:
        notify(
            job.user,
            "channel.disconnected",
            job=job,
            ctx={"channel_title": channel.channel_title or channel.youtube_channel_id, "reason": exc.code},
            payload={"channel_id": str(channel.id), "error_code": exc.code, "job_id": str(job.pk)},
        )
    except Exception:  # noqa: BLE001
        logger.exception("channel_disconnected_notification_failed", extra={"job_id": str(job.pk)})
    _fail_job(job, "channel_disconnected", f"YouTube access lost ({exc.code}): {exc}")
