"""Stage 8 — YouTube resumable upload (FR-49, FR-54..FR-57, AC-6).

`upload_job_video(job)` is the single entry point used by
`video_pipeline.tasks.upload_to_youtube`:

1. reserve quota (FR-58) — an upload that cannot be afforded is never started;
2. build an authenticated client (token refreshed first, FR-14);
3. download the final MP4 (+ thumbnail) from object storage to a temp dir;
4. `videos.insert` with `MediaFileUpload(resumable=True, chunksize=8 MiB)`,
   driving `next_chunk()` ourselves so transient HTTP/socket errors resume the
   *same* upload session instead of restarting (FR-54);
5. `thumbnails.set` when a thumbnail exists (FR-55) — a failure here is logged
   but does not fail the job, the video is already live;
6. persist `youtube_video_id` / `youtube_url` / `published_at`, move the job to
   `published`, audit `video.published`, notify the creator (FR-56).

Error taxonomy (FR-57) raised to the task:

* `YouTubeQuotaExceeded` — job must stay `upload_queued`, re-enqueue at
  `next_window`;
* `YouTubeAuthError` — `forbidden` / `invalid_grant`: channel disconnected;
* `YouTubeUploadError(retryable=True)` — FR-44 backoff ladder;
* `YouTubeUploadError(retryable=False)` — terminal `failed`.

Only the official Data API client is used (C-2). `containsSyntheticMedia` is
always sent as `True` (FR-49): every video this platform uploads is AI
generated and YouTube's disclosure is mandatory, not a preference.
"""

from __future__ import annotations

from video_pipeline.services.preferences import job_preferences

import logging
import hashlib
import socket
import tempfile
import time
from dataclasses import dataclass, field
from datetime import timezone as dt_timezone
from datetime import timedelta
from pathlib import Path

import httplib2
from django.conf import settings
from django.utils import timezone
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from channels.quota import (
    QuotaExhausted,
    mark_exhausted,
    next_quota_window,
    release_units,
    reserve_units,
)
from channels.youtube_api import (
    ChannelNotConnected,
    classify_http_error,
    youtube_client_for_channel,
)
from core.storage import get_storage
from video_pipeline.models import JobStatus, Stage, VideoJob

logger = logging.getLogger("video_pipeline.youtube_upload")

# YouTube metadata limits (Data API `videos.insert` validation rules).
TITLE_MAX_CHARS = 100
DESCRIPTION_MAX_BYTES = 5000
TAGS_MAX_TOTAL_CHARS = 500
TAG_MAX_CHARS = 30  # tags containing spaces count with quotes; keep them short
DEFAULT_CATEGORY_ID = "22"  # People & Blogs
# A publish time this far ahead is honoured via `status.publishAt` (scheduled premiere-less publish).
SCHEDULE_AHEAD_THRESHOLD = timedelta(minutes=5)

_RETRYABLE_TRANSPORT_ERRORS = (
    socket.timeout,
    ConnectionError,
    OSError,
    httplib2.HttpLib2Error,
)


class YouTubeUploadError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "youtube_upload_failed",
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class YouTubeQuotaExceeded(YouTubeUploadError):
    """FR-57/FR-58: park the job until `next_window` (aware UTC)."""

    def __init__(self, message: str, *, next_window):
        super().__init__(message, code="quota_exceeded", retryable=False)
        self.next_window = next_window


class YouTubeAuthError(YouTubeUploadError):
    """FR-57: `forbidden` / `invalid_grant` — the channel must be disconnected."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message, code=code, retryable=False)


@dataclass
class UploadResult:
    video_id: str
    url: str
    thumbnail_set: bool = False
    chunks: int = 0
    privacy_status: str = "public"
    publish_at: str | None = None
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Metadata (FR-49, AC-6)
# ---------------------------------------------------------------------------
def _sanitize_title(title: str) -> str:
    cleaned = (title or "Untitled video").replace("<", "").replace(">", "").strip()
    return cleaned[:TITLE_MAX_CHARS] or "Untitled video"


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = (text or "").encode("utf-8")
    if len(encoded) <= max_bytes:
        return text or ""
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _limit_tags(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    total = 0
    for raw in tags or []:
        tag = str(raw).replace("<", "").replace(">", "").strip()[:TAG_MAX_CHARS]
        if not tag:
            continue
        # YouTube counts quotes around multi-word tags plus a separator.
        cost = len(tag) + (2 if " " in tag else 0) + (1 if out else 0)
        if total + cost > TAGS_MAX_TOTAL_CHARS:
            break
        out.append(tag)
        total += cost
    return out


def _resolve_privacy(job: VideoJob) -> tuple[str, str | None]:
    """(privacyStatus, publishAt). A public video whose `scheduled_for` is
    still ahead is uploaded `private` with `publishAt` so YouTube flips it at
    the creator's chosen time (SPEC 5.11 `scheduled_for` = publish time).
    """
    preference = job_preferences(job)
    privacy = getattr(preference, "youtube_privacy_status", None) or "public"
    scheduled_for = job.scheduled_for
    if (
        privacy == "public"
        and scheduled_for
        and scheduled_for - timezone.now() > SCHEDULE_AHEAD_THRESHOLD
    ):
        return "private", scheduled_for.astimezone(dt_timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    return privacy, None


def build_video_body(job: VideoJob) -> dict:
    """`videos.insert` request body. AC-6: title/description/tags match the job,
    privacy honours the preference, AI disclosure is always on.
    """
    preference = job_preferences(job)
    privacy, publish_at = _resolve_privacy(job)
    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": bool(getattr(preference, "made_for_kids", False)),
        # FR-49 — non-negotiable AI-generated content disclosure.
        "containsSyntheticMedia": True,
        "embeddable": True,
    }
    if publish_at:
        status["publishAt"] = publish_at
    return {
        "snippet": {
            "title": _sanitize_title(job.title),
            "description": _truncate_utf8(job.description, DESCRIPTION_MAX_BYTES),
            "tags": _limit_tags(job.tags),
            "categoryId": str(
                getattr(preference, "youtube_category_id", "") or DEFAULT_CATEGORY_ID
            ),
            "defaultLanguage": (job.language or "en")[:10],
            "defaultAudioLanguage": (job.language or "en")[:10],
        },
        "status": status,
    }


# ---------------------------------------------------------------------------
# Resumable upload loop (FR-54)
# ---------------------------------------------------------------------------
def _translate_http_error(exc: HttpError, *, context: str) -> YouTubeUploadError:
    kind = classify_http_error(exc)
    detail = (
        f"{context}: HTTP {getattr(getattr(exc, 'resp', None), 'status', '?')} ({kind})"
    )
    if kind == "quota_exceeded":
        mark_exhausted()
        return YouTubeQuotaExceeded(detail, next_window=next_quota_window())
    if kind in ("forbidden", "invalid_grant"):
        return YouTubeAuthError(detail, code=kind)
    if kind == "retryable":
        return YouTubeUploadError(detail, code="youtube_unavailable", retryable=True)
    if kind == "not_found":
        return YouTubeUploadError(detail, code="youtube_not_found", retryable=False)
    return YouTubeUploadError(detail, code="youtube_rejected_request", retryable=False)


def _run_resumable_upload(
    request, *, job_id: str, sleep=time.sleep
) -> tuple[dict, int]:
    """Drive `request.next_chunk()` until the upload completes.

    Transient failures (5xx / rate limit / socket) retry the *current* chunk
    with exponential backoff up to `YOUTUBE_UPLOAD_MAX_CHUNK_RETRIES`; the
    resumable session is preserved so nothing already sent is re-sent.
    Returns (response, number_of_chunks_sent).
    """
    max_retries = int(settings.YOUTUBE_UPLOAD_MAX_CHUNK_RETRIES)
    response = None
    chunks = 0
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
        except HttpError as exc:
            err = _translate_http_error(exc, context="videos.insert")
            if err.retryable and retries < max_retries:
                retries += 1
                delay = min(2**retries, 60)
                logger.warning(
                    "youtube_upload_chunk_retry",
                    extra={
                        "job_id": job_id,
                        "retry": retries,
                        "delay_sec": delay,
                        "reason": str(exc),
                    },
                )
                sleep(delay)
                continue
            raise err from exc
        except _RETRYABLE_TRANSPORT_ERRORS as exc:
            if retries < max_retries:
                retries += 1
                delay = min(2**retries, 60)
                logger.warning(
                    "youtube_upload_chunk_transport_retry",
                    extra={
                        "job_id": job_id,
                        "retry": retries,
                        "delay_sec": delay,
                        "error": repr(exc),
                    },
                )
                sleep(delay)
                continue
            raise YouTubeUploadError(
                f"videos.insert transport failure after {retries} retries: {exc!r}",
                code="youtube_unavailable",
                retryable=True,
            ) from exc
        retries = 0
        chunks += 1
        if status is not None:
            logger.info(
                "youtube_upload_progress",
                extra={
                    "job_id": job_id,
                    "chunk": chunks,
                    "progress_pct": round(status.progress() * 100, 1),
                },
            )
    return response, chunks


def _set_thumbnail(youtube, *, video_id: str, path: Path, job_id: str) -> bool:
    try:
        reserve_units(units=int(settings.YOUTUBE_THUMBNAIL_COST_UNITS))
    except QuotaExhausted:
        logger.warning(
            "youtube_thumbnail_skipped_quota",
            extra={"job_id": job_id, "video_id": video_id},
        )
        return False
    media = MediaFileUpload(
        str(path), mimetype=_guess_image_mime(path), resumable=False
    )
    try:
        youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
    except HttpError as exc:
        # Custom thumbnails need a phone-verified channel; the video itself is fine.
        logger.warning(
            "youtube_thumbnail_set_failed",
            extra={
                "job_id": job_id,
                "video_id": video_id,
                "kind": classify_http_error(exc),
                "error": str(exc),
            },
        )
        return False
    except _RETRYABLE_TRANSPORT_ERRORS as exc:
        logger.warning(
            "youtube_thumbnail_set_transport_error",
            extra={"job_id": job_id, "error": repr(exc)},
        )
        return False
    return True


def _guess_image_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    return {"png": "image/png", ".png": "image/png", ".gif": "image/gif"}.get(
        suffix, "image/jpeg"
    )


# ---------------------------------------------------------------------------
# Persistence (FR-56)
# ---------------------------------------------------------------------------
def mark_job_published(job: VideoJob, result: UploadResult) -> None:
    from audit.services import record_audit_event
    from notifications.services import notify

    now = timezone.now()
    job.youtube_video_id = result.video_id[:32]
    job.youtube_url = result.url
    job.published_at = now
    job.youtube_upload_status = "uploaded"
    job.youtube_rejection_reason = ""
    job.status = JobStatus.PUBLISHED
    job.current_stage = Stage.UPLOAD
    job.completed_at = now
    job.error_code = ""
    job.error_message = ""
    meta = dict(job.script_meta or {})
    meta["youtube_privacy"] = result.privacy_status
    if result.publish_at:
        meta["youtube_publish_at"] = result.publish_at
    meta["youtube_thumbnail_set"] = result.thumbnail_set
    job.script_meta = meta
    job.save(
        update_fields=[
            "youtube_video_id",
            "youtube_url",
            "published_at",
            "youtube_upload_status",
            "youtube_rejection_reason",
            "status",
            "current_stage",
            "completed_at",
            "error_code",
            "error_message",
            "script_meta",
            "updated_at",
        ]
    )

    record_audit_event(
        actor_type="system",
        action="video.published",
        resource_type="video_job",
        resource_id=str(job.pk),
        after={
            "youtube_video_id": job.youtube_video_id,
            "youtube_url": job.youtube_url,
            "privacy_status": result.privacy_status,
            "publish_at": result.publish_at,
            "thumbnail_set": result.thumbnail_set,
            "contains_synthetic_media": True,
        },
    )
    try:
        notify(
            job.user,
            "video.published",
            job=job,
            ctx={"title": job.title, "youtube_url": job.youtube_url},
            payload={"job_id": str(job.pk), "youtube_video_id": job.youtube_video_id},
        )
    except Exception:  # noqa: BLE001 — never fail a published job on notification delivery
        logger.exception(
            "video_published_notification_failed", extra={"job_id": str(job.pk)}
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def upload_job_video(job: VideoJob, *, youtube=None, sleep=time.sleep) -> UploadResult:
    """Upload `job`'s final video to the job's channel and publish it.

    `youtube` may be injected (tests); otherwise it is built via
    `youtube_client_for_channel` (refreshing the token when needed).
    """
    job_id = str(job.pk)
    if not job.final_video_s3_key:
        raise YouTubeUploadError(
            "Job has no final video (final_video_s3_key empty).",
            code="missing_final_video",
        )

    if not job.moderation_approved_sha256:
        raise YouTubeUploadError(
            "Final video has no content-bound moderation approval.",
            code="moderation_approval_required",
        )
    from video_pipeline.services.moderation_proof import metadata_digest

    if job.moderation_metadata_sha256 != metadata_digest(job):
        raise YouTubeUploadError(
            "Public metadata changed after moderation.",
            code="moderation_metadata_changed",
        )
    upload_units = int(settings.YOUTUBE_UPLOAD_COST_UNITS)
    try:
        reserve_units(units=upload_units, uploads=1)
    except QuotaExhausted as exc:
        raise YouTubeQuotaExceeded(str(exc), next_window=exc.next_window) from exc

    reserved = True
    try:
        if youtube is None:
            try:
                youtube = youtube_client_for_channel(job.channel)
            except ChannelNotConnected as exc:
                raise YouTubeAuthError(str(exc), code="invalid_grant") from exc

        storage = get_storage()
        with tempfile.TemporaryDirectory(prefix=f"yt_upload_{job_id}_") as tmp:
            video_path = Path(tmp) / "final.mp4"
            try:
                storage.download_to(job.final_video_s3_key, video_path)
            except Exception as exc:  # noqa: BLE001 — storage errors are not YouTube errors
                raise YouTubeUploadError(
                    f"Could not download final video from storage: {exc!r}",
                    code="storage_download_failed",
                    retryable=True,
                ) from exc

            with video_path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest != job.moderation_approved_sha256:
                raise YouTubeUploadError(
                    "Video changed after moderation; a new review is required.",
                    code="moderation_content_changed",
                )

            thumbnail_path: Path | None = None
            if job.thumbnail_s3_key:
                thumbnail_path = (
                    Path(tmp)
                    / f"thumbnail{Path(job.thumbnail_s3_key).suffix or '.jpg'}"
                )
                try:
                    storage.download_to(job.thumbnail_s3_key, thumbnail_path)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "youtube_thumbnail_download_failed",
                        extra={"job_id": job_id, "error": repr(exc)},
                    )
                    thumbnail_path = None

            body = build_video_body(job)
            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                chunksize=int(settings.YOUTUBE_UPLOAD_CHUNK_SIZE_BYTES),
                resumable=True,
            )
            request = youtube.videos().insert(
                part="snippet,status", body=body, media_body=media
            )
            logger.info(
                "youtube_upload_started",
                extra={
                    "job_id": job_id,
                    "channel_id": str(job.channel_id),
                    "privacy": body["status"]["privacyStatus"],
                },
            )
            # From here on the reservation is spent whatever happens (Google charges on insert).
            reserved = False
            response, chunks = _run_resumable_upload(
                request, job_id=job_id, sleep=sleep
            )

            video_id = str(response.get("id") or "")
            if not video_id:
                raise YouTubeUploadError(
                    "videos.insert returned no video id.", code="youtube_bad_response"
                )

            result = UploadResult(
                video_id=video_id,
                url=f"https://www.youtube.com/watch?v={video_id}",
                chunks=chunks,
                privacy_status=body["status"]["privacyStatus"],
                publish_at=body["status"].get("publishAt"),
            )
            if thumbnail_path is not None:
                result.thumbnail_set = _set_thumbnail(
                    youtube, video_id=video_id, path=thumbnail_path, job_id=job_id
                )
                if not result.thumbnail_set:
                    result.warnings.append("thumbnail_not_set")
    except YouTubeQuotaExceeded:
        # Google rejected the insert on quota: our reservation is meaningless now,
        # `mark_exhausted` already pinned the counter at the limit.
        raise
    except YouTubeUploadError:
        if reserved:
            release_units(units=upload_units, uploads=1)
        raise

    mark_job_published(job, result)
    logger.info(
        "youtube_upload_succeeded",
        extra={
            "job_id": job_id,
            "video_id": video_id,
            "chunks": chunks,
            "thumbnail_set": result.thumbnail_set,
        },
    )
    return result
