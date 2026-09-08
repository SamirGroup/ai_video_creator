"""Stage 5 — FFmpeg assembly (SPEC 7.1 #5; FR-47, FR-50, A-4, A-5, AC-4).

    visual clips (one per segment) + voice.mp3 + licensed music track + intro/outro
        -> per-clip fit to its segment duration (stretch / loop / trim)
        -> concat (video only)
        -> audio graph: voice delayed by the intro, music looped + ducked under the
           voice (`sidechaincompress`), fade-out, AAC
        -> final.mp4 (H.264/AAC, 1080p by default) + thumbnail.jpg (frame at 20% + title)
        -> ffprobe sanity check (duration within tolerance, codecs, dimensions)

Layout of this module:

* **Pure planning + command builders** (`output_dimensions`, `plan_clip_fit`,
  `build_*_command`, `build_audio_filter`, `check_duration_tolerance`) — no
  FFmpeg, no DB; fully unit-tested.
* **`FFmpegAssembler`** — runs the builders through an injectable `runner`
  (`media_tools.run_command` in production, a fake in tests) inside a temp dir.
* **`assemble_video_for_job`** — the DB-aware orchestration: gathers the
  checkpoint assets, picks the music track (FR-47), runs the assembler, uploads
  `final_video` + `thumbnail`, updates `video_jobs`, appends music attribution.

Text overlays use `drawtext` with a `textfile=` (no in-filter escaping of user
titles). If the FFmpeg build lacks `drawtext`/fonts, cards degrade to plain
colour cards and the thumbnail to a bare frame — never a failed job.
"""
from __future__ import annotations

import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import transaction

from providers.exceptions import ProviderPermanentError
from video_pipeline.models import AssetKind, MusicTrack, VideoAsset
from video_pipeline.services import media_tools
from video_pipeline.services.checkpoints import (
    download_asset,
    existing_asset,
    store_file_asset,
)
from video_pipeline.services.cost_control import refresh_job_cost
from video_pipeline.services.exceptions import JobNotReady
from video_pipeline.services.script_generation import truncate_bytes
from video_pipeline.services.voice_generation import timing_from_asset

logger = logging.getLogger("video_pipeline.assembly")

OPERATION = "assembly"
FINAL_FILENAME = "final.mp4"
THUMBNAIL_FILENAME = "thumbnail.jpg"

DEFAULT_FPS = 30
DEFAULT_DIMENSIONS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
THUMBNAIL_DIMENSIONS = (1280, 720)
ENCODE_ARGS = ("-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p")
CARD_COLOUR = "0x101418"


class AssemblyError(ProviderPermanentError):
    error_code = "assembly_failed"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass
class ClipSpec:
    sequence_index: int
    path: str
    source_duration_ms: int
    target_duration_ms: int


@dataclass
class AssemblyPlan:
    clips: list[ClipSpec]
    voice_path: str
    voice_duration_ms: int
    title: str
    width: int = 1920
    height: int = 1080
    fps: int = DEFAULT_FPS
    intro_sec: float = 2.0
    outro_sec: float = 2.0
    outro_text: str = "Thanks for watching"
    music_path: str | None = None
    music_volume: float = 0.2
    fade_out_sec: float = 2.0
    font_file: str = ""
    thumbnail_position: float = 0.2

    @property
    def intro_ms(self) -> int:
        return int(round(self.intro_sec * 1000))

    @property
    def outro_ms(self) -> int:
        return int(round(self.outro_sec * 1000))

    @property
    def body_ms(self) -> int:
        return sum(c.target_duration_ms for c in self.clips)

    @property
    def total_ms(self) -> int:
        return self.intro_ms + self.body_ms + self.outro_ms


@dataclass
class AssemblyOutput:
    final_path: str
    thumbnail_path: str
    duration_ms: int
    expected_ms: int
    probe: dict = field(default_factory=dict)
    used_drawtext: bool = True
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pure planning helpers
# ---------------------------------------------------------------------------
def output_dimensions(aspect_ratio: str) -> tuple[int, int]:
    return DEFAULT_DIMENSIONS.get(aspect_ratio or "16:9", DEFAULT_DIMENSIONS["16:9"])


def plan_clip_fit(source_ms: int, target_ms: int, *, max_stretch: float = 1.5) -> tuple[str, float]:
    """Decide how a clip reaches its segment length.

    Returns `("trim", 1.0)` when the clip is long enough, `("stretch", factor)`
    when a mild slow-down (<= `max_stretch`) covers the gap — visually smoother
    than a hard loop point — and `("loop", 1.0)` otherwise.
    """
    source_ms = max(1, int(source_ms))
    target_ms = max(1, int(target_ms))
    if source_ms >= target_ms:
        return "trim", 1.0
    factor = target_ms / source_ms
    if factor <= max_stretch:
        return "stretch", round(factor, 4)
    return "loop", 1.0


def _scale_chain(width: int, height: int, fps: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p"
    )


def _seconds(ms: int) -> str:
    return f"{ms / 1000:.3f}"


def filter_path(path: str) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter option value."""
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def build_clip_fit_command(clip: ClipSpec, output_path: str, *, width: int, height: int, fps: int, max_stretch: float = 1.5) -> list[str]:
    mode, factor = plan_clip_fit(clip.source_duration_ms, clip.target_duration_ms, max_stretch=max_stretch)
    argv = [media_tools.ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error"]
    if mode == "loop":
        argv += ["-stream_loop", "-1"]
    argv += ["-i", str(clip.path)]
    vf = _scale_chain(width, height, fps)
    if mode == "stretch":
        vf = f"setpts={factor}*PTS," + vf
    argv += ["-t", _seconds(clip.target_duration_ms), "-vf", vf, "-an", *ENCODE_ARGS, str(output_path)]
    return argv


def build_card_command(output_path: str, *, duration_sec: float, width: int, height: int, fps: int, textfile: str | None = None, font_file: str = "", font_size: int | None = None) -> list[str]:
    """A solid title card. With `textfile` a centred `drawtext` overlay is added."""
    argv = [
        media_tools.ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={CARD_COLOUR}:s={width}x{height}:d={duration_sec:g}:r={fps}",
    ]
    if textfile:
        argv += ["-vf", build_drawtext(textfile, width=width, height=height, font_file=font_file, font_size=font_size)]
    argv += ["-t", f"{duration_sec:g}", *ENCODE_ARGS, str(output_path)]
    return argv


def build_drawtext(textfile: str, *, width: int, height: int, font_file: str = "", font_size: int | None = None, position: str = "center") -> str:
    size = font_size or max(24, int(min(width, height) * 0.06))
    parts = [f"textfile='{filter_path(textfile)}'"]
    if font_file:
        parts.append(f"fontfile='{filter_path(font_file)}'")
    parts += [
        "fontcolor=white",
        f"fontsize={size}",
        "line_spacing=8",
        "borderw=3",
        "bordercolor=black@0.8",
        "x=(w-text_w)/2",
    ]
    if position == "bottom":
        parts.append("y=h-text_h-h*0.08")
    else:
        parts.append("y=(h-text_h)/2")
    return "drawtext=" + ":".join(parts)


def build_concat_video_command(list_path: str, output_path: str) -> list[str]:
    return [
        media_tools.ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", "-an", str(output_path),
    ]


def build_audio_filter(*, voice_delay_ms: int, total_ms: int, has_music: bool, music_volume: float = 0.2, fade_out_ms: int = 2000, sample_rate: int = 48000) -> str:
    """`-filter_complex` graph: input 1 = voice, input 2 = music (when present).

    Ducking: music is compressed with the voice as sidechain, then the *original*
    voice is mixed on top (`asplit` keeps a clean copy). `normalize=0` keeps the
    voice level untouched by amix.
    """
    fmt = f"aformat=sample_rates={sample_rate}:channel_layouts=stereo"
    total_s = _seconds(total_ms)
    voice = f"[1:a]{fmt},adelay={voice_delay_ms}|{voice_delay_ms},apad=whole_dur={total_s}"
    if not has_music:
        return voice + "[aout]"

    fade_ms = max(0, min(int(fade_out_ms), total_ms))
    fade_start = _seconds(total_ms - fade_ms)
    music = (
        f"[2:a]{fmt},atrim=0:{total_s},asetpts=PTS-STARTPTS,volume={music_volume:g},"
        f"afade=t=out:st={fade_start}:d={_seconds(fade_ms)}[music]"
    )
    return ";".join(
        [
            voice + ",asplit=2[vmix][vsc]",
            music,
            "[music][vsc]sidechaincompress=threshold=0.015:ratio=8:attack=40:release=500:makeup=1[ducked]",
            "[vmix][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]",
        ]
    )


def build_mux_command(*, video_path: str, voice_path: str, music_path: str | None, output_path: str, filter_complex: str, total_ms: int, audio_bitrate: str = "192k") -> list[str]:
    argv = [
        media_tools.ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video_path),
        "-i", str(voice_path),
    ]
    if music_path:
        argv += ["-stream_loop", "-1", "-i", str(music_path)]
    argv += [
        "-filter_complex", filter_complex,
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "48000",
        "-t", _seconds(total_ms),
        "-movflags", "+faststart",
        str(output_path),
    ]
    return argv


def build_thumbnail_command(video_path: str, output_path: str, *, at_ms: int, textfile: str | None = None, font_file: str = "", width: int = THUMBNAIL_DIMENSIONS[0], height: int = THUMBNAIL_DIMENSIONS[1]) -> list[str]:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    if textfile:
        vf += "," + build_drawtext(textfile, width=width, height=height, font_file=font_file, font_size=int(height * 0.09), position="bottom")
    return [
        media_tools.ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", _seconds(at_ms), "-i", str(video_path),
        "-frames:v", "1", "-vf", vf, "-q:v", "2", "-update", "1", str(output_path),
    ]


def check_duration_tolerance(actual_ms: int, expected_ms: int, *, tolerance_pct: float = 10.0) -> tuple[bool, float]:
    """`(within_tolerance, deviation_pct)` for AC-4's ±10% rule."""
    if expected_ms <= 0:
        return False, 0.0
    deviation = (actual_ms - expected_ms) / expected_ms * 100
    return abs(deviation) <= tolerance_pct, round(deviation, 2)


def clips_from_timing(clip_paths: dict[int, tuple[str, int]], timing: list[dict]) -> list[ClipSpec]:
    """Zip `{sequence_index: (path, source_ms)}` with the voice `segment_timing`."""
    specs: list[ClipSpec] = []
    for entry in sorted(timing, key=lambda t: int(t.get("index") or 0)):
        index = int(entry.get("index") or 0)
        if index not in clip_paths:
            raise JobNotReady(f"Missing visual clip for segment {index}; the visuals stage is incomplete.")
        path, source_ms = clip_paths[index]
        target_ms = int(entry.get("end_ms") or 0) - int(entry.get("start_ms") or 0)
        specs.append(ClipSpec(sequence_index=index, path=path, source_duration_ms=source_ms, target_duration_ms=max(1, target_ms)))
    if not specs:
        raise JobNotReady("No segment timing available; the voice stage must run first.")
    return specs


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
class FFmpegAssembler:
    """Runs an `AssemblyPlan` to a final MP4 + thumbnail inside `workdir`."""

    def __init__(self, plan: AssemblyPlan, workdir: str, *, runner=media_tools.run_command, timeout_sec: int | None = None):
        self.plan = plan
        self.workdir = Path(workdir)
        self.runner = runner
        self.timeout = timeout_sec or int(getattr(settings, "ASSEMBLY_FFMPEG_TIMEOUT_SEC", 1800))
        self._drawtext: bool | None = None

    # -- capability probing --------------------------------------------------
    def drawtext_supported(self) -> bool:
        if self._drawtext is None:
            try:
                result = self.runner([media_tools.ffmpeg_binary(), "-hide_banner", "-filters"], timeout_sec=60, check=False)
                self._drawtext = " drawtext " in (result.stdout or "")
            except Exception:
                self._drawtext = False
        return self._drawtext

    def _textfile(self, name: str, text: str) -> str:
        path = self.workdir / f"{name}.txt"
        path.write_text(text.strip() or " ", encoding="utf-8")
        return str(path)

    # -- steps ---------------------------------------------------------------
    def _run(self, argv: list[str]):
        return self.runner(argv, timeout_sec=self.timeout)

    def _fit_clips(self) -> list[str]:
        outputs = []
        for clip in self.plan.clips:
            out = self.workdir / f"seg_{clip.sequence_index:03d}.mp4"
            self._run(build_clip_fit_command(clip, str(out), width=self.plan.width, height=self.plan.height, fps=self.plan.fps))
            outputs.append(str(out))
        return outputs

    def _card(self, name: str, text: str, duration_sec: float) -> tuple[str, bool]:
        out = self.workdir / f"{name}.mp4"
        common = {"duration_sec": duration_sec, "width": self.plan.width, "height": self.plan.height, "fps": self.plan.fps}
        if text and self.drawtext_supported():
            try:
                self._run(build_card_command(str(out), textfile=self._textfile(name, text), font_file=self.plan.font_file, **common))
                return str(out), True
            except media_tools.MediaToolError:
                logger.warning("assembly_drawtext_failed_falling_back", extra={"card": name})
        self._run(build_card_command(str(out), **common))
        return str(out), False

    def assemble(self) -> AssemblyOutput:
        plan = self.plan
        used_drawtext = True

        segments = self._fit_clips()
        parts: list[str] = []
        if plan.intro_sec > 0:
            intro, ok = self._card("intro", plan.title, plan.intro_sec)
            used_drawtext = used_drawtext and ok
            parts.append(intro)
        parts += segments
        if plan.outro_sec > 0:
            outro, ok = self._card("outro", plan.outro_text, plan.outro_sec)
            used_drawtext = used_drawtext and ok
            parts.append(outro)

        list_path = media_tools.write_concat_list(parts, str(self.workdir / "video_concat.txt"))
        video_track = self.workdir / "video_track.mp4"
        self._run(build_concat_video_command(list_path, str(video_track)))

        final_path = self.workdir / FINAL_FILENAME
        graph = build_audio_filter(
            voice_delay_ms=plan.intro_ms,
            total_ms=plan.total_ms,
            has_music=bool(plan.music_path),
            music_volume=plan.music_volume,
            fade_out_ms=int(plan.fade_out_sec * 1000),
        )
        self._run(
            build_mux_command(
                video_path=str(video_track),
                voice_path=plan.voice_path,
                music_path=plan.music_path,
                output_path=str(final_path),
                filter_complex=graph,
                total_ms=plan.total_ms,
            )
        )

        probe = media_tools.probe(str(final_path), runner=self.runner)
        duration_ms = media_tools.duration_ms_from_probe(probe)
        tolerance = float(getattr(settings, "ASSEMBLY_DURATION_TOLERANCE_PCT", 10))
        within, deviation = check_duration_tolerance(duration_ms, plan.total_ms, tolerance_pct=tolerance)
        if not within:
            raise AssemblyError(
                f"Assembled video is {duration_ms} ms but {plan.total_ms} ms was expected "
                f"({deviation:+.1f}%, tolerance ±{tolerance:g}%)."
            )

        thumb_path = self.workdir / THUMBNAIL_FILENAME
        at_ms = int(duration_ms * plan.thumbnail_position)
        thumb_text = self._textfile("thumbnail", plan.title) if plan.title and self.drawtext_supported() else None
        try:
            self._run(build_thumbnail_command(str(final_path), str(thumb_path), at_ms=at_ms, textfile=thumb_text, font_file=plan.font_file))
        except media_tools.MediaToolError:
            if thumb_text is None:
                raise
            logger.warning("assembly_thumbnail_drawtext_failed_falling_back")
            used_drawtext = False
            self._run(build_thumbnail_command(str(final_path), str(thumb_path), at_ms=at_ms))

        video_info = media_tools.video_stream_info(probe)
        audio_info = media_tools.audio_stream_info(probe)
        return AssemblyOutput(
            final_path=str(final_path),
            thumbnail_path=str(thumb_path),
            duration_ms=duration_ms,
            expected_ms=plan.total_ms,
            probe=probe,
            used_drawtext=used_drawtext,
            meta={
                "width": video_info.get("width"),
                "height": video_info.get("height"),
                "video_codec": video_info.get("codec_name"),
                "audio_codec": audio_info.get("codec_name"),
                "fps": plan.fps,
                "intro_ms": plan.intro_ms,
                "outro_ms": plan.outro_ms,
                "music": bool(plan.music_path),
                "duration_deviation_pct": deviation,
                "clip_fits": [
                    {"sequence_index": c.sequence_index, **dict(zip(("mode", "factor"), plan_clip_fit(c.source_duration_ms, c.target_duration_ms)))}
                    for c in plan.clips
                ],
            },
        )


# ---------------------------------------------------------------------------
# Music selection (FR-47, A-5)
# ---------------------------------------------------------------------------
def select_music_track(job) -> MusicTrack | None:
    """Deterministic pick from the licensed library: prefer the preference's
    `music_style` as mood, fall back to any active track, `"none"` disables music.
    """
    style = ((job.preference.music_style if job.preference else "") or "").strip().lower()
    if style in ("none", "off", "no_music"):
        return None
    queryset = MusicTrack.objects.filter(is_active=True)
    candidates = list(queryset.filter(mood__iexact=style).order_by("title", "id")) if style else []
    if not candidates:
        candidates = list(queryset.order_by("title", "id"))
    if not candidates:
        return None
    return candidates[uuid.UUID(str(job.pk)).int % len(candidates)]


def attribution_line(track: MusicTrack) -> str:
    text = (track.attribution_text or "").strip() or f"Music: {track.title} ({track.license_type})"
    return text if text.lower().startswith("music") else f"Music: {text}"


def append_attribution(description: str, track: MusicTrack | None, *, max_bytes: int = 5000) -> str:
    """FR-47: licensed tracks that require attribution get it in the description,
    exactly once, within YouTube's 5000-byte description limit.
    """
    if track is None or not track.attribution_required:
        return description
    line = attribution_line(track)
    if line in (description or ""):
        return description
    body = (description or "").rstrip()
    combined = f"{body}\n\n{line}" if body else line
    if len(combined.encode("utf-8")) <= max_bytes:
        return combined
    budget = max_bytes - len(("\n\n" + line).encode("utf-8"))
    return truncate_bytes(body, max(0, budget)) + "\n\n" + line


# ---------------------------------------------------------------------------
# DB-aware orchestration
# ---------------------------------------------------------------------------
@dataclass
class AssembledJob:
    final_asset: VideoAsset
    thumbnail_asset: VideoAsset
    duration_ms: int
    music_track: MusicTrack | None = None
    skipped: bool = False
    meta: dict = field(default_factory=dict)


def _gather_inputs(job, tmp_path: Path):
    voice_asset = existing_asset(job, AssetKind.AUDIO_VOICE)
    if voice_asset is None:
        raise JobNotReady(f"Video job {job.pk} has no voice-over checkpoint — the voice stage must run first.")
    timing = [t.to_dict() for t in timing_from_asset(voice_asset)]
    if not timing:
        raise JobNotReady(f"Video job {job.pk} voice asset has no segment_timing.")

    clip_assets = list(VideoAsset.objects.filter(job=job, kind=AssetKind.VISUAL_CLIP).exclude(sequence_index=None).order_by("sequence_index"))
    if not clip_assets:
        raise JobNotReady(f"Video job {job.pk} has no visual clips — the visuals stage must run first.")

    voice_path = download_asset(voice_asset, tmp_path / "voice.mp3")
    clip_paths: dict[int, tuple[str, int]] = {}
    for asset in clip_assets:
        path = download_asset(asset, tmp_path / f"clip_{asset.sequence_index:03d}.mp4")
        clip_paths[int(asset.sequence_index)] = (str(path), int(asset.duration_ms or 0))
    return voice_asset, timing, clip_paths, voice_path


def assemble_video_for_job(job, *, runner=media_tools.run_command, workdir: str | None = None) -> AssembledJob:
    existing_final = existing_asset(job, AssetKind.FINAL_VIDEO)
    existing_thumb = existing_asset(job, AssetKind.THUMBNAIL)
    if existing_final is not None and existing_thumb is not None:
        logger.info("assembly_stage_skipped_checkpoint_exists", extra={"job_id": str(job.pk)})
        _apply_to_job(job, existing_final, existing_thumb, description=job.description)
        return AssembledJob(existing_final, existing_thumb, int(existing_final.duration_ms or 0), skipped=True, meta=dict(existing_final.metadata or {}))

    preference = job.preference
    aspect_ratio = (preference.aspect_ratio if preference else "") or "16:9"
    width, height = output_dimensions(aspect_ratio)
    track = select_music_track(job)

    with tempfile.TemporaryDirectory(prefix=f"assembly_{job.pk}_", dir=workdir) as tmp:
        tmp_path = Path(tmp)
        voice_asset, timing, clip_paths, voice_path = _gather_inputs(job, tmp_path)

        music_path = None
        if track is not None:
            try:
                from core.storage import get_storage

                music_path = str(get_storage().download_to(track.s3_key, tmp_path / "music.mp3"))
            except Exception:
                logger.warning("assembly_music_download_failed_continuing_without", extra={"job_id": str(job.pk), "track_id": str(track.id)})
                track = None

        # Clips whose duration was not probed at generation time get measured now.
        for index, (path, source_ms) in list(clip_paths.items()):
            if source_ms <= 0:
                clip_paths[index] = (path, media_tools.probe_duration_ms(path, runner=runner))

        plan = AssemblyPlan(
            clips=clips_from_timing(clip_paths, timing),
            voice_path=str(voice_path),
            voice_duration_ms=int(voice_asset.duration_ms or 0),
            title=job.title or "",
            width=width,
            height=height,
            fps=int(getattr(settings, "ASSEMBLY_FPS", DEFAULT_FPS)),
            intro_sec=float(getattr(settings, "ASSEMBLY_INTRO_SEC", 2.0)),
            outro_sec=float(getattr(settings, "ASSEMBLY_OUTRO_SEC", 2.0)),
            outro_text=str(getattr(settings, "ASSEMBLY_OUTRO_TEXT", "Thanks for watching")),
            music_path=music_path,
            music_volume=float(getattr(settings, "ASSEMBLY_MUSIC_VOLUME", 0.2)),
            font_file=str(getattr(settings, "ASSEMBLY_FONT_FILE", "") or ""),
        )
        output = FFmpegAssembler(plan, str(tmp_path), runner=runner).assemble()

        target_sec = int(getattr(preference, "video_duration_sec", 0) or 0) if preference else 0
        within_target, target_deviation = check_duration_tolerance(output.duration_ms, target_sec * 1000) if target_sec else (True, 0.0)
        if not within_target:
            # AC-4 wants ±10% of the preference; the narration length decides that, so
            # this is surfaced (metadata + warning) rather than failing a paid job.
            logger.warning(
                "assembly_duration_outside_preference_target",
                extra={"job_id": str(job.pk), "duration_ms": output.duration_ms, "target_sec": target_sec, "deviation_pct": target_deviation},
            )

        meta = {
            **output.meta,
            "aspect_ratio": aspect_ratio,
            "expected_ms": output.expected_ms,
            "target_duration_sec": target_sec,
            "target_deviation_pct": target_deviation,
            "within_target_tolerance": within_target,
            "used_drawtext": output.used_drawtext,
            "music_track_id": str(track.id) if track else None,
        }
        final_asset = store_file_asset(job, AssetKind.FINAL_VIDEO, output.final_path, filename=FINAL_FILENAME, mime_type="video/mp4", duration_ms=output.duration_ms, provider="ffmpeg", metadata=meta)
        thumb_asset = store_file_asset(job, AssetKind.THUMBNAIL, output.thumbnail_path, filename=THUMBNAIL_FILENAME, mime_type="image/jpeg", provider="ffmpeg", metadata={"at_ms": int(output.duration_ms * plan.thumbnail_position), "used_drawtext": output.used_drawtext})
        if track is not None:
            VideoAsset.objects.update_or_create(
                job=job,
                kind=AssetKind.AUDIO_MUSIC,
                sequence_index=None,
                defaults={
                    "s3_key": track.s3_key,
                    "mime_type": "audio/mpeg",
                    "duration_ms": track.duration_ms,
                    "provider": "music_library",
                    "license_ref": f"music_tracks:{track.id}",
                    "metadata": {"title": track.title, "license_type": track.license_type, "attribution_required": track.attribution_required, "mood": track.mood},
                },
            )

    _apply_to_job(job, final_asset, thumb_asset, description=append_attribution(job.description, track))
    logger.info("assembly_stage_succeeded", extra={"job_id": str(job.pk), "duration_ms": output.duration_ms, "music": bool(track)})
    return AssembledJob(final_asset, thumb_asset, output.duration_ms, music_track=track, meta=meta)


@transaction.atomic
def _apply_to_job(job, final_asset: VideoAsset, thumb_asset: VideoAsset, *, description: str) -> None:
    job.final_video_s3_key = final_asset.s3_key
    job.thumbnail_s3_key = thumb_asset.s3_key
    job.duration_sec = int(round((final_asset.duration_ms or 0) / 1000))
    job.description = description
    job.save(update_fields=["final_video_s3_key", "thumbnail_s3_key", "duration_sec", "description", "updated_at"])
    refresh_job_cost(job)
