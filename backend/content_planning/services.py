"""Content planning services (FR-33..FR-37): preference CRUD, pause/resume,
publish-slot computation, manual "Generate now" and job cancellation.

Every state change is audited; views never touch models directly.
"""

from __future__ import annotations

import logging
from datetime import timezone as dt_timezone
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from audit.services import record_audit_event
from billing.quota import release_quota, reserve_quota
from channels.models import ConnectionStatus, YouTubeChannel
from content_planning.models import ContentPreference, Frequency
from contracts.gates import assert_generation_allowed

logger = logging.getLogger("content_planning.services")


class PreferenceConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "PREFERENCES_EXIST"
    default_detail = (
        "This channel already has content preferences. Use PATCH to change them."
    )


class PreferencesRequired(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "PREFERENCES_REQUIRED"
    default_detail = (
        "Set up content preferences for this channel before generating videos."
    )


class ChannelNotConnected(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "CHANNEL_NOT_CONNECTED"
    default_detail = (
        "The YouTube channel is not connected. Reconnect it to generate videos."
    )


class JobNotCancelable(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "JOB_NOT_CANCELABLE"
    default_detail = "This job can no longer be canceled."


# ---------------------------------------------------------------------------
# Lookups (owner-scoped, no IDOR)
# ---------------------------------------------------------------------------
def get_owned_channel(user, channel_id) -> YouTubeChannel:
    channel = YouTubeChannel.objects.filter(
        id=channel_id, user=user, deleted_at__isnull=True
    ).first()
    if channel is None:
        raise NotFound("Channel not found.")
    return channel


def get_preference(channel: YouTubeChannel) -> ContentPreference | None:
    return (
        ContentPreference.objects.filter(channel=channel, deleted_at__isnull=True)
        .order_by("created_at")
        .first()
    )


def _snapshot(pref: ContentPreference) -> dict:
    return {
        "niche": pref.niche,
        "language": pref.language,
        "video_duration_sec": pref.video_duration_sec,
        "frequency": pref.frequency,
        "publish_time_local": pref.publish_time_local.isoformat(),
        "publish_timezone": pref.publish_timezone,
        "publish_days": pref.publish_days,
        "approval_mode": pref.approval_mode,
        "youtube_privacy_status": pref.youtube_privacy_status,
        "is_paused": pref.is_paused,
    }


# ---------------------------------------------------------------------------
# Preference CRUD (FR-33, FR-34)
# ---------------------------------------------------------------------------
@transaction.atomic
def create_preference(
    user, channel: YouTubeChannel, data: dict, request=None
) -> ContentPreference:
    if get_preference(channel) is not None:
        raise PreferenceConflict()  # one preference per channel in MVP (A-1)
    pref = ContentPreference.objects.create(user=user, channel=channel, **data)
    record_audit_event(
        actor_type="user",
        actor_id=user.id,
        action="content_preferences.created",
        resource_type="content_preference",
        resource_id=str(pref.id),
        request=request,
        after=_snapshot(pref),
    )
    return pref


@transaction.atomic
def update_preference(
    pref: ContentPreference, data: dict, request=None
) -> ContentPreference:
    before = _snapshot(pref)
    for field, value in data.items():
        setattr(pref, field, value)
    pref.save()
    record_audit_event(
        actor_type="user",
        actor_id=pref.user_id,
        action="content_preferences.updated",
        resource_type="content_preference",
        resource_id=str(pref.id),
        request=request,
        before=before,
        after=_snapshot(pref),
    )
    return pref


def _set_paused(
    pref: ContentPreference, paused: bool, request=None
) -> ContentPreference:
    if pref.is_paused == paused:
        return pref
    pref.is_paused = paused
    pref.save(update_fields=["is_paused", "updated_at"])
    record_audit_event(
        actor_type="user",
        actor_id=pref.user_id,
        action="content_preferences.paused"
        if paused
        else "content_preferences.resumed",
        resource_type="content_preference",
        resource_id=str(pref.id),
        request=request,
        after={"is_paused": paused},
    )
    return pref


def pause_preference(pref: ContentPreference, request=None) -> ContentPreference:
    """FR-36: stop the scheduler for this channel. Already-scheduled jobs stay
    `scheduled` and are simply not enqueued while paused."""
    return _set_paused(pref, True, request)


def resume_preference(pref: ContentPreference, request=None) -> ContentPreference:
    return _set_paused(pref, False, request)


# ---------------------------------------------------------------------------
# Publish-slot computation (FR-35)
# ---------------------------------------------------------------------------
def next_publish_slot(pref: ContentPreference, now: datetime | None = None) -> datetime:
    """First publish datetime strictly after `now`, in UTC, honouring the
    preference's local time, timezone and frequency rule.

    * daily   — every day at `publish_time_local`
    * weekly  — on each weekday in `publish_days` (0=Monday .. 6=Sunday)
    * monthly — on day-of-month `publish_days[0]` (default 1st)
    """
    now = now or timezone.now()
    tz = ZoneInfo(pref.publish_timezone)
    local_now = now.astimezone(tz)
    t = pref.publish_time_local

    if pref.frequency == Frequency.WEEKLY:
        weekdays = set(pref.publish_days or [local_now.weekday()])
        matches = lambda d: d.weekday() in weekdays  # noqa: E731
    elif pref.frequency == Frequency.MONTHLY:
        day_of_month = (pref.publish_days or [1])[0]
        matches = lambda d: d.day == day_of_month  # noqa: E731
    else:
        matches = lambda d: True  # noqa: E731

    for offset in range(0, 62):
        day = (local_now + timedelta(days=offset)).date()
        if not matches(day):
            continue
        candidate = datetime.combine(day, t, tzinfo=tz)
        if candidate > local_now:
            return candidate.astimezone(dt_timezone.utc)
    raise ValueError(f"Could not compute a publish slot for preference {pref.id}")


def generation_start_for(scheduled_for: datetime) -> datetime:
    """When the pipeline must start so the video is ready by `scheduled_for`."""
    return scheduled_for - timedelta(
        minutes=settings.PIPELINE_EXPECTED_DURATION_MINUTES
    )


# ---------------------------------------------------------------------------
# Manual generate / cancel (FR-36)
# ---------------------------------------------------------------------------
def _enqueue_script_stage(job_id: str) -> None:
    from video_pipeline.tasks import generate_script

    generate_script.apply_async(args=[str(job_id)], queue="q_script")


def generate_now(user, channel: YouTubeChannel, request=None):
    """Create a `queued` job right away (quota reserved atomically) and enqueue stage 1."""
    from video_pipeline.models import JobStatus, JobTrigger, VideoJob

    assert_generation_allowed(user)
    if channel.status != ConnectionStatus.CONNECTED:
        raise ChannelNotConnected()
    pref = get_preference(channel)
    if pref is None:
        raise PreferencesRequired()

    now = timezone.now()
    with transaction.atomic():
        job = VideoJob.objects.create(
            user=user,
            channel=channel,
            preference=pref,
            trigger=JobTrigger.MANUAL,
            status=JobStatus.QUEUED,
            scheduled_for=now,
            language=pref.language,
            duration_sec=pref.video_duration_sec,
        )
        reserve_quota(
            user, kind="video", job=job
        )  # raises 402/409 -> transaction rolled back
        record_audit_event(
            actor_type="user",
            actor_id=user.id,
            action="video_job.generate_now",
            resource_type="video_job",
            resource_id=str(job.id),
            request=request,
            after={
                "status": job.status,
                "channel_id": str(channel.id),
                "preference_id": str(pref.id),
            },
        )
        transaction.on_commit(lambda job_id=str(job.id): _enqueue_script_stage(job_id))
    logger.info(
        "video_job_generate_now", extra={"job_id": str(job.id), "user_id": str(user.id)}
    )
    return job


def cancel_job(user, job, request=None):
    """Creator cancel (SPEC 7.2). Quota is refunded only when generation has not started."""
    from video_pipeline.models import JobStatus

    if job.is_terminal() or job.status in (JobStatus.UPLOADING, JobStatus.UPLOADED):
        raise JobNotCancelable(f"Job is {job.status} and cannot be canceled.")

    before_status = job.status
    quota_refunded = False
    with transaction.atomic():
        if job.started_at is None:
            quota_refunded = release_quota(user, job) is not None
        job.status = JobStatus.CANCELED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at", "updated_at"])
        record_audit_event(
            actor_type="user",
            actor_id=user.id,
            action="video_job.canceled",
            resource_type="video_job",
            resource_id=str(job.id),
            request=request,
            before={"status": before_status},
            after={"status": job.status, "quota_refunded": quota_refunded},
        )
    logger.info(
        "video_job_canceled",
        extra={"job_id": str(job.id), "quota_refunded": quota_refunded},
    )
    return job
