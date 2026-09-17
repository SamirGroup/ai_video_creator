"""Stage 6 — final (visual) moderation gate (SPEC 7.1 #6; FR-46, FR-48, A-15, C-6).

    final.mp4 -> ffmpeg keyframes every N seconds -> AWS Rekognition
    DetectModerationLabels per frame -> worst-case merge -> verdict -> ModerationLog(stage=final)

The narration was already moderated at stage 2 (FR-45) and the voice-over is a
verbatim rendering of it, so the audio half of "keyframe'lar + audio" reuses that
verdict rather than paying for a transcript (SPEC 9: Whisper is F2).

Provider selection: Rekognition is a *second* moderation provider next to OpenAI
Moderation. `api_credentials_config` allows one primary per service, so this
module selects its row explicitly by `(service="moderation", provider="aws_rekognition")`
instead of `get_primary_config`. Thresholds live in that row's `config`.

Scores are Rekognition confidences scaled to 0..1 so `evaluate_scores` from the
script gate (block/flag/category thresholds) is reused unchanged.
"""

from __future__ import annotations

import logging
import tempfile
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from django.conf import settings

from moderation.models import ModerationLog, ModerationStage, ModerationVerdict
from providers.exceptions import (
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderRetryableError,
    ProviderTimeoutError,
)
from providers.models import ApiCredentialConfig, ServiceType
from providers.services import record_api_usage
from video_pipeline.models import AssetKind
from video_pipeline.services import media_tools
from video_pipeline.services.checkpoints import download_asset, existing_asset
from video_pipeline.services.cost_control import refresh_job_cost, unit_cost
from video_pipeline.services.exceptions import JobNotReady
from video_pipeline.services.script_moderation import evaluate_scores

logger = logging.getLogger("video_pipeline.visual_moderation")

OPERATION = "final_moderation"
REKOGNITION_PROVIDER = "aws_rekognition"

DEFAULT_BLOCK_THRESHOLD = 0.8
DEFAULT_FLAG_THRESHOLD = 0.6
DEFAULT_KEYFRAME_INTERVAL_SEC = 5
DEFAULT_MAX_FRAMES = 60
RETRYABLE_AWS_CODES = {
    "ThrottlingException",
    "ProvisionedThroughputExceededException",
    "InternalServerError",
    "ServiceUnavailable",
    "RequestTimeout",
    "LimitExceededException",
}
AUTH_AWS_CODES = {
    "AccessDeniedException",
    "UnrecognizedClientException",
    "InvalidSignatureException",
    "ExpiredTokenException",
}


@dataclass
class FrameLabels:
    frame: str
    labels: list[dict]
    latency_ms: int


@dataclass
class FinalModerationOutcome:
    verdict: str
    max_category: str
    max_score: float
    category_scores: dict
    thresholds: dict
    frames_checked: int
    raw_response: dict = field(default_factory=dict)

    @property
    def is_blocking(self) -> bool:
        return self.verdict in (ModerationVerdict.FLAG, ModerationVerdict.BLOCK)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def keyframe_interval(
    duration_ms: int, *, base_interval_sec: float, max_frames: int
) -> float:
    """Sample every `base_interval_sec`, stretching the interval so a long video
    never exceeds `max_frames` Rekognition calls (cost + 5-minute stage budget).
    """
    duration_sec = max(1.0, duration_ms / 1000)
    interval = max(0.5, float(base_interval_sec))
    if max_frames > 0 and duration_sec / interval > max_frames:
        interval = duration_sec / max_frames
    return round(interval, 3)


def label_scores(labels_by_frame: list[list[dict]]) -> tuple[dict, dict]:
    """Worst-case merge: per label name (and parent name) the max confidence/100.
    Returns `(scores, hits)` where `hits` counts frames per label for the log.
    """
    scores: dict[str, float] = {}
    hits: dict[str, int] = {}
    for labels in labels_by_frame:
        seen: set[str] = set()
        for label in labels or []:
            if not isinstance(label, dict):
                continue
            try:
                confidence = float(label.get("Confidence") or 0) / 100.0
            except (TypeError, ValueError):
                continue
            for name in (label.get("Name"), label.get("ParentName")):
                if not name:
                    continue
                name = str(name)
                if confidence > scores.get(name, -1.0):
                    scores[name] = round(confidence, 4)
                if name not in seen:
                    hits[name] = hits.get(name, 0) + 1
                    seen.add(name)
    return scores, hits


def resolve_thresholds(config: ApiCredentialConfig) -> dict:
    return {
        "block_threshold": float(
            config.get_option(
                "block_threshold",
                getattr(
                    settings,
                    "FINAL_MODERATION_BLOCK_THRESHOLD",
                    DEFAULT_BLOCK_THRESHOLD,
                ),
            )
        ),
        "flag_threshold": float(
            config.get_option(
                "flag_threshold",
                getattr(
                    settings, "FINAL_MODERATION_FLAG_THRESHOLD", DEFAULT_FLAG_THRESHOLD
                ),
            )
        ),
        "category_thresholds": dict(config.get_option("category_thresholds", {}) or {}),
    }


def get_rekognition_config() -> ApiCredentialConfig:
    config = (
        ApiCredentialConfig.objects.filter(
            service=ServiceType.MODERATION,
            provider=REKOGNITION_PROVIDER,
            is_active=True,
            deleted_at__isnull=True,
        )
        .order_by("priority", "created_at")
        .first()
    )
    if config is None:
        raise ProviderNotConfigured(
            "No active api_credentials_config row for service='moderation', provider='aws_rekognition' (FR-46)."
        )
    return config


# ---------------------------------------------------------------------------
# Provider client
# ---------------------------------------------------------------------------
class RekognitionModerator:
    """boto3 `rekognition.detect_moderation_labels` over local JPEG frames.

    Credentials come from `settings.AWS_REKOGNITION_*` (separate key pair from
    storage); when they are empty boto3's default chain (instance role) applies.
    """

    def __init__(self, config: ApiCredentialConfig, *, client=None):
        self.config = config
        self.min_confidence = float(config.get_option("min_confidence", 50))
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3

            kwargs = {
                "region_name": getattr(settings, "AWS_REKOGNITION_REGION", "us-east-1")
            }
            access_key = getattr(settings, "AWS_REKOGNITION_ACCESS_KEY_ID", "")
            if access_key:
                kwargs["aws_access_key_id"] = access_key
                kwargs["aws_secret_access_key"] = getattr(
                    settings, "AWS_REKOGNITION_SECRET_ACCESS_KEY", ""
                )
            self._client = boto3.client("rekognition", **kwargs)
        return self._client

    def detect(self, image_bytes: bytes) -> FrameLabels:
        started = time.monotonic()
        try:
            response = self.client.detect_moderation_labels(
                Image={"Bytes": image_bytes}, MinConfidence=self.min_confidence
            )
        except (
            Exception
        ) as exc:  # botocore exceptions are mapped by name/code, no hard import
            raise self._map_exception(exc) from exc
        latency_ms = int((time.monotonic() - started) * 1000)
        labels = response.get("ModerationLabels") or []
        return FrameLabels(frame="", labels=list(labels), latency_ms=latency_ms)

    @staticmethod
    def _map_exception(exc: Exception) -> Exception:
        code = ""
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = str((response.get("Error") or {}).get("Code") or "")
        name = exc.__class__.__name__
        if code in AUTH_AWS_CODES:
            return ProviderAuthError(f"Rekognition rejected the credentials ({code}).")
        if code in RETRYABLE_AWS_CODES or name in (
            "EndpointConnectionError",
            "ConnectionClosedError",
            "ReadTimeoutError",
            "ConnectTimeoutError",
        ):
            if "Throttl" in code or "Exceeded" in code:
                return ProviderRateLimitError(
                    f"Rekognition throttled the request ({code})."
                )
            if "Timeout" in name or "Timeout" in code:
                return ProviderTimeoutError(f"Rekognition request timed out ({name}).")
            return ProviderRetryableError(f"Rekognition unavailable ({code or name}).")
        if name == "NoCredentialsError" or name == "PartialCredentialsError":
            return ProviderNotConfigured(
                "AWS Rekognition credentials are not configured (AWS_REKOGNITION_*)."
            )
        return ProviderPermanentError(
            f"Rekognition rejected the request ({code or name}).",
            error_code="moderation_request_rejected",
        )


# ---------------------------------------------------------------------------
# DB-aware orchestration
# ---------------------------------------------------------------------------
def extract_keyframes(
    video_path: str,
    out_dir: str,
    *,
    interval_sec: float,
    runner=media_tools.run_command,
) -> list[Path]:
    pattern = str(Path(out_dir) / "frame_%04d.jpg")
    runner(
        media_tools.build_keyframe_extract_command(
            video_path, pattern, interval_sec=interval_sec
        ),
        timeout_sec=600,
    )
    return sorted(Path(out_dir).glob("frame_*.jpg"))


def moderate_final_video_for_job(
    job, *, moderator=None, runner=media_tools.run_command, workdir: str | None = None
) -> FinalModerationOutcome:
    """Run the FR-46 gate over the assembled video and persist a `moderation_logs` row."""
    final_asset = existing_asset(job, AssetKind.FINAL_VIDEO)
    if final_asset is None:
        raise JobNotReady(
            f"Video job {job.pk} has no final video — the assembly stage must run first."
        )

    config = get_rekognition_config()
    moderator = moderator or RekognitionModerator(config)
    thresholds = resolve_thresholds(config)
    interval = keyframe_interval(
        int(final_asset.duration_ms or 0),
        base_interval_sec=float(
            config.get_option(
                "keyframe_interval_sec",
                getattr(
                    settings,
                    "FINAL_MODERATION_KEYFRAME_INTERVAL_SEC",
                    DEFAULT_KEYFRAME_INTERVAL_SEC,
                ),
            )
        ),
        max_frames=int(
            config.get_option(
                "max_frames",
                getattr(settings, "FINAL_MODERATION_MAX_FRAMES", DEFAULT_MAX_FRAMES),
            )
        ),
    )

    labels_by_frame: list[list[dict]] = []
    frame_results: list[dict] = []
    total_latency = 0
    with tempfile.TemporaryDirectory(prefix=f"finalmod_{job.pk}_", dir=workdir) as tmp:
        tmp_path = Path(tmp)
        video_path = download_asset(final_asset, tmp_path / "final.mp4")
        frames = extract_keyframes(
            str(video_path), str(tmp_path), interval_sec=interval, runner=runner
        )
        if not frames:
            raise ProviderPermanentError(
                "Keyframe extraction produced no frames.",
                error_code="keyframe_extraction_failed",
            )

        for frame in frames:
            try:
                result = moderator.detect(frame.read_bytes())
            except Exception as exc:
                record_api_usage(
                    config=config,
                    operation=OPERATION,
                    job=job,
                    user=job.user,
                    units=len(frame_results),
                    unit_type="images",
                    cost_usd=unit_cost(
                        config, len(frame_results), expected_unit="per_request"
                    ),
                    http_status=getattr(exc, "http_status", None),
                    success=False,
                    error_code=getattr(exc, "error_code", exc.__class__.__name__),
                )
                raise
            total_latency += result.latency_ms
            labels_by_frame.append(result.labels)
            frame_results.append({"frame": frame.name, "labels": result.labels})

    scores, hits = label_scores(labels_by_frame)
    verdict, category, score = evaluate_scores(scores, **thresholds)

    record_api_usage(
        config=config,
        operation=OPERATION,
        job=job,
        user=job.user,
        units=len(frame_results),
        unit_type="images",
        cost_usd=unit_cost(config, len(frame_results), expected_unit="per_request"),
        latency_ms=total_latency,
        http_status=200,
        success=True,
    )
    refresh_job_cost(job)

    raw = {
        "frames": frame_results,
        "interval_sec": interval,
        "hits": hits,
        "min_confidence": moderator.min_confidence,
    }
    ModerationLog.objects.create(
        job=job,
        stage=ModerationStage.FINAL,
        provider=config.provider,
        verdict=verdict,
        categories=scores,
        threshold_config={
            **thresholds,
            "max_category": category,
            "max_score": score,
            "frames_checked": len(frame_results),
            "script_verdict_reused_for_audio": True,
        },
        raw_response=raw,
    )
    logger.info(
        "final_moderation_completed",
        extra={
            "job_id": str(job.pk),
            "verdict": verdict,
            "max_category": category,
            "max_score": round(score, 4),
            "frames": len(frame_results),
        },
    )
    return FinalModerationOutcome(
        verdict=verdict,
        max_category=category,
        max_score=score,
        category_scores=scores,
        thresholds=thresholds,
        frames_checked=len(frame_results),
        raw_response=raw,
    )


def apply_final_verdict_to_job(job, outcome: FinalModerationOutcome) -> str:
    """SPEC 7.2: pass -> approval flow (review_required -> awaiting_approval, auto ->
    upload_queued); flag/block -> moderation_review (never auto-published, FR-48).
    """
    from video_pipeline.models import JobStatus
    from video_pipeline.services import approval

    if outcome.verdict == ModerationVerdict.PASS:
        return approval.on_final_moderation_passed(job)

    if outcome.verdict == ModerationVerdict.BLOCK and getattr(
        settings, "MODERATION_AUTO_REJECT_ON_BLOCK", False
    ):
        new_status = JobStatus.MODERATION_REJECTED
    else:
        new_status = JobStatus.MODERATION_REVIEW

    job.status = new_status
    job.error_code = "final_moderation_flagged"
    job.error_message = (
        f"Final moderation verdict={outcome.verdict} category={outcome.max_category or 'n/a'} "
        f"score={round(outcome.max_score, 4)} over {outcome.frames_checked} keyframes."
    )
    job.save(update_fields=["status", "error_code", "error_message", "updated_at"])

    try:
        from notifications.services import notify_admins

        notify_admins(
            "admin.alert",
            job=job,
            ctx={
                "subject": "Video needs moderator review",
                "message": f"Job {job.pk} ({job.title!r}) final moderation verdict={outcome.verdict}, category={outcome.max_category or 'n/a'}.",
            },
            payload={
                "job_id": str(job.pk),
                "verdict": outcome.verdict,
                "stage": "final",
            },
        )
    except Exception:  # alerting must never undo the gate decision
        logger.exception(
            "final_moderation_admin_alert_failed", extra={"job_id": str(job.pk)}
        )
    from video_pipeline.services.revisions import maybe_auto_revise

    maybe_auto_revise(job, outcome)
    return job.status


def cost_for_frames(config: ApiCredentialConfig, frames: int) -> Decimal:
    return unit_cost(config, frames, expected_unit="per_request")
