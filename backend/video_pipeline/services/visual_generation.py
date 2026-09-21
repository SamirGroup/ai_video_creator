"""Stage 4 — per-segment visual clips (SPEC 7.1 #4; FR-42, FR-43, FR-51, FR-52).

The most expensive and slowest stage, so three protections are built in:

* **FR-52 before every provider call.** `check_cost_ceiling(job)` runs before
  each task is created; a job that crosses the ceiling stops with the clips it
  already paid for intact.
* **Per-segment checkpoints.** Each clip is its own `VideoAsset(kind=visual_clip,
  sequence_index=n)`; a retry only generates the missing ones.
* **Task-id resume.** Created-but-not-downloaded Runway task ids are persisted in
  `job.script_meta["visual_tasks"]`, so a worker crash while polling re-polls
  instead of re-creating (and re-paying for) the task.

Clip length comes from the voice stage's `segment_timing` (falling back to the
script's `target_duration_sec`); assembly loops/trims to the exact segment.
"""

from __future__ import annotations

from video_pipeline.services.stage_lock import serialized_paid_stage

from video_pipeline.services.preferences import job_preferences

import logging
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from providers.exceptions import ProviderError, ProviderRetryableError
from providers.models import ServiceType
from providers.services import get_primary_config, record_api_usage
from video_pipeline.models import AssetKind, VideoAsset
from video_pipeline.services import media_tools
from video_pipeline.services.checkpoints import existing_asset, store_file_asset
from video_pipeline.services.cost_control import check_cost_ceiling, unit_cost
from video_pipeline.services.exceptions import JobNotReady
from video_pipeline.services.video_gen_client import RunwayClient
from video_pipeline.services.voice_generation import load_segments, timing_from_asset

logger = logging.getLogger("video_pipeline.visuals")

OPERATION = "visual_generation"
PENDING_TASKS_KEY = "visual_tasks"


@dataclass
class ClipPlan:
    sequence_index: int
    prompt: str
    target_duration_ms: int
    heading: str = ""


@dataclass
class VisualsResult:
    clips: list[VideoAsset]
    generated: int = 0
    skipped: int = 0
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def build_clip_plan(
    segments: list[dict], timing: list[dict] | None, *, default_duration_sec: int = 10
) -> list[ClipPlan]:
    """Pair every script segment with its measured voice duration (or the
    scripted target when the voice stage has not measured it).
    """
    by_index = {}
    for entry in timing or []:
        try:
            by_index[int(entry["index"])] = int(entry["end_ms"]) - int(
                entry["start_ms"]
            )
        except (KeyError, TypeError, ValueError):
            continue

    plan: list[ClipPlan] = []
    for position, segment in enumerate(segments, start=1):
        duration_ms = by_index.get(position)
        if not duration_ms or duration_ms <= 0:
            try:
                duration_ms = int(float(segment.get("target_duration_sec") or 0)) * 1000
            except (TypeError, ValueError):
                duration_ms = 0
        if duration_ms <= 0:
            duration_ms = default_duration_sec * 1000
        prompt = (
            str(segment.get("visual_prompt") or "").strip()
            or str(segment.get("narration") or "").strip()
        )
        plan.append(
            ClipPlan(
                sequence_index=position,
                prompt=prompt,
                target_duration_ms=duration_ms,
                heading=str(segment.get("heading") or ""),
            )
        )
    return plan


def style_prompt(prompt: str, *, style_suffix: str = "") -> str:
    prompt = prompt.strip()
    if style_suffix and style_suffix.lower() not in prompt.lower():
        return f"{prompt}. {style_suffix.strip()}"
    return prompt


# ---------------------------------------------------------------------------
# DB-aware orchestration
# ---------------------------------------------------------------------------
def _pending_tasks(job) -> dict:
    raw = (job.script_meta or {}).get(PENDING_TASKS_KEY) or {}
    return {str(k): v for k, v in raw.items()} if isinstance(raw, dict) else {}


def _save_pending_tasks(job, pending: dict) -> None:
    meta = dict(job.script_meta or {})
    if pending:
        meta[PENDING_TASKS_KEY] = pending
    else:
        meta.pop(PENDING_TASKS_KEY, None)
    job.script_meta = meta
    job.save(update_fields=["script_meta", "updated_at"])


def _record_failure(config, job, clip: ClipPlan, exc: Exception, *, units: int) -> None:
    record_api_usage(
        config=config,
        operation=OPERATION,
        job=job,
        user=job.user,
        units=units,
        unit_type="seconds",
        cost_usd=Decimal("0"),
        http_status=getattr(exc, "http_status", None),
        success=False,
        error_code=getattr(exc, "error_code", exc.__class__.__name__),
    )




@serialized_paid_stage
def generate_visuals_for_job(
    job, *, client=None, runner=media_tools.run_command, workdir: str | None = None
) -> VisualsResult:
    """Generate every missing `visual_clip` for `job` (FR-43 per-segment checkpoints)."""
    segments = load_segments(job)
    voice_asset = existing_asset(job, AssetKind.AUDIO_VOICE)
    if voice_asset is None:
        raise JobNotReady(
            f"Video job {job.pk} has no voice-over checkpoint — the voice stage must run first."
        )
    timing = [t.to_dict() for t in timing_from_asset(voice_asset)]

    config = None
    subscription = getattr(job.user, "subscription", None)
    if subscription and subscription.plan.ai_budget_enabled:
        from providers.models import ApiCredentialConfig
        from providers.exceptions import ProviderNotConfigured

        models = subscription.plan.features.get("video_models", [])
        selected = (job.generation_context or {}).get("video_model") or (
            models[0] if models else ""
        )
        if selected not in models:
            raise ProviderNotConfigured("Video model is not included in this plan.")
        config = ApiCredentialConfig.objects.filter(
            service=ServiceType.VIDEO_GEN,
            provider__in=["runway", "higgsfield"],
            model_name=selected,
            is_active=True,
        ).first()
        if config is None:
            raise ProviderNotConfigured("The selected plan model is not activated.")
    if config is None:
        config = get_primary_config(ServiceType.VIDEO_GEN)
    from video_pipeline.services.higgsfield_client import HiggsfieldClient

    client = client or (HiggsfieldClient(config) if config.provider == "higgsfield" else RunwayClient(config))
    aspect_ratio = (
        job_preferences(job).aspect_ratio if job_preferences(job) else ""
    ) or "16:9"
    style_suffix = str(config.get_option("style_suffix", "") or "")

    plan = build_clip_plan(segments, timing)
    pending = _pending_tasks(job)
    clips: list[VideoAsset] = []
    generated = skipped = 0

    with tempfile.TemporaryDirectory(prefix=f"visuals_{job.pk}_", dir=workdir) as tmp:
        tmp_path = Path(tmp)
        for clip in plan:
            existing = existing_asset(
                job, AssetKind.VISUAL_CLIP, sequence_index=clip.sequence_index
            )
            if existing is not None:
                clips.append(existing)
                skipped += 1
                continue

            key = str(clip.sequence_index)
            task_info = pending.get(key)
            task_id = task_info.get("id") if isinstance(task_info, dict) else task_info
            requested_duration = (
                task_info.get("duration", 0) if isinstance(task_info, dict) else 0
            )
            if task_id:
                logger.info(
                    "visual_task_resumed",
                    extra={
                        "job_id": str(job.pk),
                        "sequence_index": clip.sequence_index,
                    },
                )
            else:
                from billing.wallet import ensure_job_call_budget, reserve_job

                reserve_job(job)
                check_cost_ceiling(job)
                from video_pipeline.services.video_gen_client import pick_clip_duration

                estimated_seconds = pick_clip_duration(
                    clip.target_duration_ms / 1000, client.allowed_durations
                )
                ensure_job_call_budget(
                    job,
                    unit_cost(config, estimated_seconds, expected_unit="per_second"),
                )
                try:
                    task = client.create_task(
                        prompt=style_prompt(clip.prompt, style_suffix=style_suffix),
                        target_duration_sec=clip.target_duration_ms / 1000,
                        aspect_ratio=aspect_ratio,
                    )
                except Exception as exc:
                    _record_failure(config, job, clip, exc, units=0)
                    raise
                task_id = task.task_id
                requested_duration = task.duration_sec
                pending[key] = {
                    "id": task_id,
                    "duration": requested_duration,
                    "price_per_second": str(
                        unit_cost(config, 1, expected_unit="per_second")
                    ),
                }
                if isinstance(client, HiggsfieldClient):
                    pending[key]["status_url"] = client.status_urls[task_id]
                _save_pending_tasks(job, pending)

            if isinstance(client, HiggsfieldClient) and isinstance(pending.get(key), dict):
                status_url = pending[key].get("status_url")
                if status_url:
                    client.status_urls[task_id] = status_url
            try:
                result = client.wait_for_task(task_id)
                from video_pipeline.services.video_gen_client import pick_clip_duration

                billed_seconds = requested_duration or pick_clip_duration(
                    clip.target_duration_ms / 1000, client.allowed_durations
                )
                info = pending.get(key)
                price = (
                    Decimal(info["price_per_second"])
                    if isinstance(info, dict)
                    else unit_cost(config, 1, expected_unit="per_second")
                )
                record_api_usage(
                    config=config,
                    operation=OPERATION,
                    job=job,
                    user=job.user,
                    units=billed_seconds,
                    unit_type="seconds",
                    cost_usd=price * Decimal(billed_seconds),
                    http_status=200,
                    success=True,
                    request_id=task_id,
                )
                data = client.download(result.output_urls[0])
            except ProviderRetryableError as exc:
                # Re-fetch task outputs on retry; never buy a new generation just
                # because its temporary download URL expired.
                _record_failure(config, job, clip, exc, units=requested_duration)
                raise
            except ProviderError as exc:
                pending.pop(key, None)
                _save_pending_tasks(job, pending)
                _record_failure(config, job, clip, exc, units=requested_duration)
                raise

            clip_path = tmp_path / f"clip_{clip.sequence_index:03d}.mp4"
            clip_path.write_bytes(data)
            try:
                duration_ms = media_tools.probe_duration_ms(
                    str(clip_path), runner=runner
                )
            except ProviderError:
                duration_ms = (
                    requested_duration or int(round(clip.target_duration_ms / 1000))
                ) * 1000
            asset = store_file_asset(
                job,
                AssetKind.VISUAL_CLIP,
                clip_path,
                filename=clip_path.name,
                mime_type="video/mp4",
                duration_ms=duration_ms,
                provider=config.provider,
                sequence_index=clip.sequence_index,
                metadata={
                    "task_id": task_id,
                    "prompt": clip.prompt,
                    "heading": clip.heading,
                    "target_duration_ms": clip.target_duration_ms,
                    "requested_duration_sec": billed_seconds,
                    "aspect_ratio": aspect_ratio,
                    "model": config.model_name,
                },
            )
            clips.append(asset)
            generated += 1
            pending.pop(key, None)
            _save_pending_tasks(job, pending)

    total_cost = check_cost_ceiling(job)
    logger.info(
        "visuals_stage_succeeded",
        extra={
            "job_id": str(job.pk),
            "generated": generated,
            "skipped": skipped,
            "total_cost_usd": str(total_cost),
        },
    )
    return VisualsResult(
        clips=sorted(clips, key=lambda a: a.sequence_index or 0),
        generated=generated,
        skipped=skipped,
        meta={
            "provider": config.provider,
            "model": config.model_name,
            "aspect_ratio": aspect_ratio,
        },
    )
