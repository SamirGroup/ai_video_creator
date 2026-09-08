"""Stage 9 — post-publish checks (FR-59, FR-60).

* `check_recent_uploads()` — for every job published within the last
  `YOUTUBE_POST_PUBLISH_WINDOW_HOURS` whose YouTube status is not final yet,
  `videos.list(part="status,processingDetails")` and map YouTube's
  `uploadStatus` / `rejectionReason` / `failureReason` onto
  `video_jobs.youtube_upload_status` + `youtube_rejection_reason`. A rejected
  video moves the job to `youtube_rejected` and notifies the creator at once.
* `sync_published_videos()` — for every platform-published video, batch
  `videos.list` (50 ids per call, 1 quota unit each); ids YouTube no longer
  returns (or reports as `deleted`) are flagged `deleted_on_youtube` (revenue
  excludes them); privacy changes are recorded in
  `script_meta["youtube_privacy"]`.

Both run per channel (each channel has its own OAuth credentials) and stop
early on quota exhaustion; a disconnected channel is skipped.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from googleapiclient.errors import HttpError

from channels.models import ConnectionStatus, YouTubeChannel
from channels.quota import QuotaExhausted, reserve_units
from channels.youtube_api import ChannelNotConnected, classify_http_error, youtube_client_for_channel
from video_pipeline.models import JobStatus, VideoJob

logger = logging.getLogger("video_pipeline.youtube_status")

BATCH_SIZE = 50  # videos.list `id` accepts up to 50 comma-separated ids
FINAL_UPLOAD_STATUSES = {"processed", "rejected", "deleted"}


@dataclass
class SweepReport:
    checked: int = 0
    processed: int = 0
    rejected: int = 0
    deleted: int = 0
    privacy_changed: int = 0
    skipped_channels: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "checked": self.checked,
            "processed": self.processed,
            "rejected": self.rejected,
            "deleted": self.deleted,
            "privacy_changed": self.privacy_changed,
            "skipped_channels": self.skipped_channels,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# YouTube -> job mapping
# ---------------------------------------------------------------------------
def interpret_video_item(item: dict) -> tuple[str, str]:
    """(youtube_upload_status, youtube_rejection_reason) for a `videos.list` item.

    YouTube `status.uploadStatus`: uploaded | processed | failed | rejected | deleted.
    `rejectionReason`: claim, copyright, duplicate, inappropriate, legal, length,
    termsOfUse, trademark, uploaderAccountClosed, uploaderAccountSuspended.
    `failureReason`: codec, conversion, emptyFile, invalidFile, tooSmall, uploadAborted.
    """
    status = item.get("status") or {}
    upload_status = str(status.get("uploadStatus") or "").lower()
    if upload_status == "processed":
        return "processed", ""
    if upload_status == "rejected":
        return "rejected", str(status.get("rejectionReason") or "rejected")[:64]
    if upload_status == "failed":
        return "rejected", f"upload_failed:{status.get('failureReason') or 'unknown'}"[:64]
    if upload_status == "deleted":
        return "deleted", ""
    return "uploaded", ""


def apply_processing_result(job: VideoJob, item: dict, *, report: SweepReport | None = None) -> str:
    """Persist one `videos.list` item onto `job`. Returns the new upload status."""
    report = report or SweepReport()
    upload_status, reason = interpret_video_item(item)
    processing = (item.get("processingDetails") or {}).get("processingStatus")
    privacy = (item.get("status") or {}).get("privacyStatus")

    meta = dict(job.script_meta or {})
    if processing:
        meta["youtube_processing"] = processing
    fields = ["youtube_upload_status", "youtube_rejection_reason", "script_meta", "updated_at"]

    if upload_status == "deleted":
        _mark_deleted(job, report)
        return "deleted"

    if privacy and meta.get("youtube_privacy") != privacy:
        if meta.get("youtube_privacy"):
            report.privacy_changed += 1
        meta["youtube_privacy"] = privacy

    job.youtube_upload_status = upload_status
    job.youtube_rejection_reason = reason
    job.script_meta = meta

    if upload_status == "rejected":
        job.status = JobStatus.YOUTUBE_REJECTED
        job.error_code = "youtube_rejected"
        job.error_message = f"YouTube rejected the video: {reason}"
        job.completed_at = job.completed_at or timezone.now()
        fields += ["status", "error_code", "error_message", "completed_at"]
        job.save(update_fields=fields)
        _notify_rejected(job, reason)
        report.rejected += 1
        return "rejected"

    job.save(update_fields=fields)
    if upload_status == "processed":
        report.processed += 1
    return upload_status


def _mark_deleted(job: VideoJob, report: SweepReport) -> None:
    """FR-60: the creator removed the video on YouTube -> excluded from revenue."""
    from audit.services import record_audit_event

    if job.deleted_on_youtube:
        return
    job.deleted_on_youtube = True
    job.youtube_upload_status = "deleted"
    job.status = JobStatus.DELETED_ON_YOUTUBE
    job.save(update_fields=["deleted_on_youtube", "youtube_upload_status", "status", "updated_at"])
    record_audit_event(
        actor_type="system",
        action="video.deleted_on_youtube",
        resource_type="video_job",
        resource_id=str(job.pk),
        metadata={"youtube_video_id": job.youtube_video_id},
    )
    report.deleted += 1


def _notify_rejected(job: VideoJob, reason: str) -> None:
    from audit.services import record_audit_event
    from notifications.services import notify

    record_audit_event(
        actor_type="system",
        action="video.youtube_rejected",
        resource_type="video_job",
        resource_id=str(job.pk),
        metadata={"youtube_video_id": job.youtube_video_id, "reason": reason},
    )
    try:
        notify(
            job.user,
            "video.youtube_rejected",
            job=job,
            ctx={"title": job.title, "reason": reason},
            payload={"job_id": str(job.pk), "youtube_video_id": job.youtube_video_id, "reason": reason},
        )
    except Exception:  # noqa: BLE001
        logger.exception("youtube_rejected_notification_failed", extra={"job_id": str(job.pk)})


# ---------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------
def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _list_videos(youtube, ids: list[str], *, part: str) -> dict[str, dict]:
    """One `videos.list` call (1 unit). Returns {video_id: item}."""
    reserve_units(units=int(settings.YOUTUBE_LIST_COST_UNITS))
    response = youtube.videos().list(part=part, id=",".join(ids), maxResults=BATCH_SIZE).execute()
    return {str(item.get("id")): item for item in response.get("items") or [] if item.get("id")}


def _sweep_channel_jobs(
    channel: YouTubeChannel, jobs: list[VideoJob], *, part: str, report: SweepReport, missing_is_deleted: bool
) -> None:
    try:
        youtube = youtube_client_for_channel(channel)
    except ChannelNotConnected:
        report.skipped_channels += 1
        return

    for batch in _chunks(jobs, BATCH_SIZE):
        ids = [job.youtube_video_id for job in batch]
        try:
            items = _list_videos(youtube, ids, part=part)
        except QuotaExhausted as exc:
            report.errors.append(f"quota_exhausted:{exc.kind}")
            logger.warning("youtube_status_sweep_quota_exhausted", extra={"channel_id": str(channel.id)})
            raise
        except HttpError as exc:
            kind = classify_http_error(exc)
            report.errors.append(f"{channel.id}:{kind}")
            logger.warning(
                "youtube_status_sweep_http_error",
                extra={"channel_id": str(channel.id), "kind": kind, "error": str(exc)},
            )
            if kind == "invalid_grant":
                from channels.services import _mark_channel_disconnected_after_refresh_failure

                _mark_channel_disconnected_after_refresh_failure(channel, error_code=kind)
            if kind == "quota_exceeded":
                from channels.quota import mark_exhausted

                mark_exhausted()
                raise QuotaExhausted(
                    project_id=settings.GOOGLE_CLOUD_PROJECT_ID, kind="units", used=0, limit=0,
                    next_window=timezone.now(),
                ) from exc
            return  # skip the rest of this channel, continue with others

        for job in batch:
            report.checked += 1
            item = items.get(job.youtube_video_id)
            if item is None:
                if missing_is_deleted:
                    _mark_deleted(job, report)
                else:
                    logger.info(
                        "youtube_status_video_not_listed",
                        extra={"job_id": str(job.pk), "youtube_video_id": job.youtube_video_id},
                    )
                continue
            try:
                apply_processing_result(job, item, report=report)
            except Exception as exc:  # noqa: BLE001 — one bad row must not stop the sweep
                report.errors.append(f"{job.pk}:{exc!r}")
                logger.exception("youtube_status_apply_failed", extra={"job_id": str(job.pk)})


def _group_by_channel(jobs) -> dict[YouTubeChannel, list[VideoJob]]:
    grouped: dict[YouTubeChannel, list[VideoJob]] = {}
    for job in jobs:
        grouped.setdefault(job.channel, []).append(job)
    return grouped


def check_recent_uploads(*, now=None) -> SweepReport:
    """FR-59: poll processing status for videos published in the last 24h."""
    now = now or timezone.now()
    window_start = now - timedelta(hours=int(settings.YOUTUBE_POST_PUBLISH_WINDOW_HOURS))
    jobs = (
        VideoJob.objects.select_related("channel", "user")
        .filter(
            published_at__gte=window_start,
            deleted_on_youtube=False,
            channel__status=ConnectionStatus.CONNECTED,
        )
        .exclude(youtube_video_id="")
        .exclude(youtube_upload_status__in=FINAL_UPLOAD_STATUSES)
        .order_by("published_at")
    )
    report = SweepReport()
    for channel, channel_jobs in _group_by_channel(jobs).items():
        try:
            _sweep_channel_jobs(
                channel, channel_jobs, part="status,processingDetails", report=report, missing_is_deleted=True
            )
        except QuotaExhausted:
            break
    logger.info("check_recent_uploads_done", extra=report.as_dict())
    return report


def sync_published_videos() -> SweepReport:
    """FR-60: detect creator-side deletions / privacy changes for every
    platform-published video still counted for revenue.
    """
    jobs = (
        VideoJob.objects.select_related("channel", "user")
        .filter(
            status__in=[JobStatus.PUBLISHED],
            deleted_on_youtube=False,
            channel__status=ConnectionStatus.CONNECTED,
        )
        .exclude(youtube_video_id="")
        .order_by("published_at")
    )
    report = SweepReport()
    for channel, channel_jobs in _group_by_channel(jobs).items():
        try:
            _sweep_channel_jobs(channel, channel_jobs, part="status", report=report, missing_is_deleted=True)
        except QuotaExhausted:
            break
    logger.info("sync_published_videos_done", extra=report.as_dict())
    return report
