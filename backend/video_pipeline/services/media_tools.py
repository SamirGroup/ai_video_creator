"""Thin FFmpeg / ffprobe wrappers shared by the voice, assembly and final-moderation
stages (SPEC 9 "FFmpeg", FR-50).

Design rule: **command building is pure, command execution is one function.**
Every stage builds an argv list with a `build_*` helper (unit-tested without
FFmpeg) and hands it to `run_command`, which tests replace with a fake. The
binaries come from `settings.FFMPEG_BINARY` / `settings.FFPROBE_BINARY` so a
deployment can point at a specific build without touching PATH.

Nothing here logs command output verbatim: FFmpeg's stderr can include input
paths, which for signed-URL inputs would leak the signature (NFR-3). We keep the
last few lines only, on failure, and the paths are local temp files anyway.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from providers.exceptions import ProviderPermanentError, ProviderRetryableError

logger = logging.getLogger("video_pipeline.media")


class MediaToolError(ProviderPermanentError):
    """FFmpeg/ffprobe returned a non-zero exit code or unusable output."""

    error_code = "media_tool_failed"


class MediaToolTimeout(ProviderRetryableError):
    """FFmpeg exceeded its wall-clock budget — usually a stuck worker, worth one retry."""

    error_code = "media_tool_timeout"


def ffmpeg_binary() -> str:
    return getattr(settings, "FFMPEG_BINARY", "ffmpeg") or "ffmpeg"


def ffprobe_binary() -> str:
    return getattr(settings, "FFPROBE_BINARY", "ffprobe") or "ffprobe"


def ffmpeg_available() -> bool:
    """True when both binaries resolve (either absolute paths or on PATH)."""
    return all(
        (Path(binary).is_file() or shutil.which(binary) is not None)
        for binary in (ffmpeg_binary(), ffprobe_binary())
    )


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def run_command(argv: list[str], *, timeout_sec: int | None = None, check: bool = True) -> CommandResult:
    """Execute `argv` and return its captured output.

    Raises `MediaToolError` on a non-zero exit (with a short stderr tail) and
    `MediaToolTimeout` if the process outlives `timeout_sec`.
    """
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MediaToolError(
            f"{argv[0]} is not installed or not on PATH (set FFMPEG_BINARY/FFPROBE_BINARY).",
            error_code="media_tool_missing",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaToolTimeout(f"{argv[0]} exceeded {timeout_sec}s.") from exc

    result = CommandResult(
        argv=tuple(argv),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
    if check and completed.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-5:])
        raise MediaToolError(f"{Path(argv[0]).name} exited with code {completed.returncode}: {tail}")
    return result


# ---------------------------------------------------------------------------
# ffprobe
# ---------------------------------------------------------------------------
def build_probe_command(path: str) -> list[str]:
    return [
        ffprobe_binary(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]


def parse_probe_output(stdout: str) -> dict:
    try:
        data = json.loads(stdout or "{}")
    except ValueError as exc:
        raise MediaToolError("ffprobe returned a non-JSON body.") from exc
    if not isinstance(data, dict):
        raise MediaToolError("ffprobe returned an unexpected JSON type.")
    return data


def probe(path: str, *, runner=run_command) -> dict:
    return parse_probe_output(runner(build_probe_command(path), timeout_sec=60).stdout)


def duration_ms_from_probe(data: dict) -> int:
    """Container duration first, longest stream second. Raises when neither is usable."""
    candidates: list[float] = []
    fmt = data.get("format") or {}
    try:
        candidates.append(float(fmt.get("duration")))
    except (TypeError, ValueError):
        pass
    for stream in data.get("streams") or []:
        try:
            candidates.append(float(stream.get("duration")))
        except (TypeError, ValueError):
            continue
    candidates = [c for c in candidates if c > 0]
    if not candidates:
        raise MediaToolError("ffprobe reported no duration for the media file.")
    return int(round(max(candidates) * 1000))


def probe_duration_ms(path: str, *, runner=run_command) -> int:
    return duration_ms_from_probe(probe(path, runner=runner))


def video_stream_info(data: dict) -> dict:
    """`{width, height, codec_name, r_frame_rate}` of the first video stream (or {})."""
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video":
            return {
                "width": int(stream.get("width") or 0),
                "height": int(stream.get("height") or 0),
                "codec_name": stream.get("codec_name") or "",
                "r_frame_rate": stream.get("r_frame_rate") or "",
            }
    return {}


def audio_stream_info(data: dict) -> dict:
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "audio":
            return {
                "codec_name": stream.get("codec_name") or "",
                "sample_rate": int(stream.get("sample_rate") or 0),
                "channels": int(stream.get("channels") or 0),
            }
    return {}


# ---------------------------------------------------------------------------
# Generic ffmpeg builders reused by more than one stage
# ---------------------------------------------------------------------------
def write_concat_list(paths: list[str], list_path: str) -> str:
    """Write an ffmpeg concat-demuxer list. Single quotes in paths are escaped
    the way the demuxer expects; backslashes are normalised so Windows paths work.
    """
    lines = []
    for path in paths:
        normalised = str(path).replace("\\", "/").replace("'", r"'\''")
        lines.append(f"file '{normalised}'")
    Path(list_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list_path


def build_concat_audio_command(list_path: str, output_path: str, *, bitrate: str = "128k") -> list[str]:
    """Concatenate same-format audio files, re-encoding once so segment boundaries
    are clean (a `-c copy` MP3 concat leaves audible glitches at frame edges).
    """
    return [
        ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-vn",
        "-c:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(output_path),
    ]


def build_keyframe_extract_command(
    video_path: str, output_pattern: str, *, interval_sec: float, max_width: int = 1280
) -> list[str]:
    """One JPEG every `interval_sec` seconds (FR-46 keyframes for Rekognition)."""
    interval_sec = max(0.5, float(interval_sec))
    return [
        ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"fps=1/{interval_sec:g},scale='min({max_width},iw)':-2",
        "-q:v",
        "3",
        str(output_pattern),
    ]
