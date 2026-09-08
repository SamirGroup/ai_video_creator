"""Stage 3 — voice-over (SPEC 7.1 #3; FR-42, FR-43, FR-51).

    VideoAsset(kind=script).metadata["segments"]
        -> one ElevenLabs call per segment (tts_client)
        -> ffprobe each segment -> segment_timing [{index, start_ms, end_ms}]
        -> ffmpeg concat -> voice.mp3
        -> VideoAsset(kind=audio_voice, metadata={segment_timing, ...})

`segment_timing` is the contract with the visuals and assembly stages: each
visual clip is fitted to `end_ms - start_ms` of its segment, so audio and
picture stay in sync without a transcript (SPEC 9: "MVP'da TTS timing
metadata yetarli").

Checkpoint (FR-43): if the `audio_voice` asset already exists in storage the
provider is not called again. Per-segment audio is kept only in the temp dir —
TTS is cheap and fast relative to the visuals stage, so partial checkpoints are
not worth the storage churn.
"""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from providers.models import ServiceType
from providers.services import get_primary_config, record_api_usage
from video_pipeline.models import AssetKind, VideoAsset
from video_pipeline.services import media_tools
from video_pipeline.services.checkpoints import existing_asset, store_file_asset
from video_pipeline.services.cost_control import check_cost_ceiling, unit_cost
from video_pipeline.services.exceptions import JobNotReady
from video_pipeline.services.tts_client import ElevenLabsClient

logger = logging.getLogger("video_pipeline.voice")

OPERATION = "voice_generation"
VOICE_FILENAME = "voice.mp3"


@dataclass
class SegmentTiming:
    index: int
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict:
        return {"index": self.index, "start_ms": self.start_ms, "end_ms": self.end_ms}


@dataclass
class VoiceResult:
    asset: VideoAsset
    segment_timing: list[SegmentTiming]
    total_duration_ms: int
    characters: int = 0
    skipped: bool = False
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def load_segments(job) -> list[dict]:
    """Ordered narration segments from the stage-1 checkpoint. Raises `JobNotReady`
    when the script stage has not produced them.
    """
    asset = VideoAsset.objects.filter(job=job, kind=AssetKind.SCRIPT).order_by("-created_at").first()
    segments = list((asset.metadata or {}).get("segments") or []) if asset else []
    segments = [s for s in segments if isinstance(s, dict) and str(s.get("narration") or "").strip()]
    if not segments:
        raise JobNotReady(
            f"Video job {job.pk} has no script segments — the script stage must run first (FR-42)."
        )
    segments.sort(key=lambda s: int(s.get("index") or 0))
    return segments


def compute_segment_timing(durations_ms: list[int], *, gap_ms: int = 0) -> list[SegmentTiming]:
    """Cumulative start/end offsets for consecutive segments."""
    timing: list[SegmentTiming] = []
    cursor = 0
    for position, duration in enumerate(durations_ms, start=1):
        duration = max(0, int(duration))
        timing.append(SegmentTiming(index=position, start_ms=cursor, end_ms=cursor + duration))
        cursor += duration + max(0, int(gap_ms))
    return timing


def resolve_voice_id(job, config) -> str:
    preference = getattr(job, "preference", None)
    voice = (getattr(preference, "voice_id", "") or "").strip() if preference else ""
    return voice or str(config.get_option("default_voice_id", "") or "")


def timing_from_asset(asset: VideoAsset) -> list[SegmentTiming]:
    raw = (asset.metadata or {}).get("segment_timing") or []
    return [
        SegmentTiming(index=int(t.get("index") or i + 1), start_ms=int(t.get("start_ms") or 0), end_ms=int(t.get("end_ms") or 0))
        for i, t in enumerate(raw)
        if isinstance(t, dict)
    ]


# ---------------------------------------------------------------------------
# DB-aware orchestration
# ---------------------------------------------------------------------------
def _synthesize_and_log(client, config, job, text: str, *, voice_id: str, language: str):
    try:
        result = client.synthesize(text, voice_id=voice_id, language_code=language)
    except Exception as exc:
        record_api_usage(
            config=config,
            operation=OPERATION,
            job=job,
            user=job.user,
            units=len(text),
            unit_type="chars",
            cost_usd=Decimal("0"),
            http_status=getattr(exc, "http_status", None),
            success=False,
            error_code=getattr(exc, "error_code", exc.__class__.__name__),
        )
        raise

    record_api_usage(
        config=config,
        operation=OPERATION,
        job=job,
        user=job.user,
        units=result.characters,
        unit_type="chars",
        cost_usd=unit_cost(config, result.characters, expected_unit="per_char"),
        latency_ms=result.latency_ms,
        http_status=result.http_status,
        success=True,
        request_id=result.request_id,
    )
    return result


def generate_voice_for_job(job, *, client=None, runner=media_tools.run_command, workdir: str | None = None) -> VoiceResult:
    """Synthesize, concatenate and checkpoint the voice-over for `job`."""
    existing = existing_asset(job, AssetKind.AUDIO_VOICE)
    if existing is not None:
        logger.info("voice_stage_skipped_checkpoint_exists", extra={"job_id": str(job.pk)})
        timing = timing_from_asset(existing)
        return VoiceResult(
            asset=existing,
            segment_timing=timing,
            total_duration_ms=int(existing.duration_ms or (timing[-1].end_ms if timing else 0)),
            skipped=True,
            meta=dict(existing.metadata or {}),
        )

    segments = load_segments(job)
    config = get_primary_config(ServiceType.TTS)
    client = client or ElevenLabsClient(config)
    voice_id = resolve_voice_id(job, config)
    language = job.language or (job.preference.language if job.preference else "") or "en"
    gap_ms = int(config.get_option("segment_gap_ms", 0) or 0)

    check_cost_ceiling(job)

    with tempfile.TemporaryDirectory(prefix=f"voice_{job.pk}_", dir=workdir) as tmp:
        tmp_path = Path(tmp)
        segment_files: list[str] = []
        durations_ms: list[int] = []
        characters = 0

        for position, segment in enumerate(segments, start=1):
            text = str(segment.get("narration") or "").strip()
            result = _synthesize_and_log(client, config, job, text, voice_id=voice_id, language=language)
            characters += result.characters
            segment_path = tmp_path / f"segment_{position:03d}.mp3"
            segment_path.write_bytes(result.audio)
            segment_files.append(str(segment_path))
            durations_ms.append(media_tools.probe_duration_ms(str(segment_path), runner=runner))

        timing = compute_segment_timing(durations_ms, gap_ms=gap_ms)
        total_ms = timing[-1].end_ms if timing else 0

        output_path = tmp_path / VOICE_FILENAME
        if len(segment_files) == 1 and gap_ms == 0:
            Path(segment_files[0]).replace(output_path)
        else:
            list_path = media_tools.write_concat_list(segment_files, str(tmp_path / "concat.txt"))
            runner(media_tools.build_concat_audio_command(list_path, str(output_path)), timeout_sec=600)

        # Measure the concatenated file: it is what assembly will actually use.
        try:
            total_ms = media_tools.probe_duration_ms(str(output_path), runner=runner)
        except media_tools.MediaToolError:
            logger.warning("voice_concat_probe_failed_using_sum", extra={"job_id": str(job.pk)})

        meta = {
            "provider": config.provider,
            "model": client.model_id if hasattr(client, "model_id") else config.model_name,
            "voice_id": voice_id,
            "segment_count": len(segments),
            "segment_gap_ms": gap_ms,
            "characters": characters,
            "segment_timing": [t.to_dict() for t in timing],
        }
        asset = store_file_asset(
            job,
            AssetKind.AUDIO_VOICE,
            output_path,
            filename=VOICE_FILENAME,
            mime_type="audio/mpeg",
            duration_ms=total_ms,
            provider=config.provider,
            metadata=meta,
        )

    total_cost = check_cost_ceiling(job)
    logger.info(
        "voice_stage_succeeded",
        extra={
            "job_id": str(job.pk),
            "segments": len(segments),
            "characters": characters,
            "duration_ms": total_ms,
            "total_cost_usd": str(total_cost),
        },
    )
    return VoiceResult(
        asset=asset, segment_timing=timing, total_duration_ms=total_ms, characters=characters, meta=meta
    )
