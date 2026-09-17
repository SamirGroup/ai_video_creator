"""Approval flow (FR-38..FR-41, SPEC 7.2, AC-6): the human-in-the-loop gate
between final moderation passing and the YouTube upload stage.

Two entry points:
* System-triggered — `on_final_moderation_passed(job)`, called by
  `video_pipeline.services.visual_moderation.apply_final_verdict_to_job` the
  moment stage 6 (final moderation) returns `pass`. Routes the job to
  `awaiting_approval` (review_required, FR-38) or straight to the upload
  queue (`upload_queued` -> `upload_to_youtube`, auto mode, FR-40) per
  `ContentPreference.approval_mode`.
* Creator-triggered — `approve_job`, `reject_job`, `request_changes`,
  `update_metadata`, `ensure_preview_token`, called by `video_pipeline.views`.

Also `expire_stale_approvals()` — the FR-38 48-hour timeout sweep, wired as a
Celery Beat periodic task in `video_pipeline.tasks.expire_stale_approvals`.

Self-service actions a creator takes on their own job (approve/reject/request
changes) are audit-logged but do not self-notify, matching the precedent in
`content_planning.services.cancel_job`. Only genuinely async events the
creator might miss (a video is ready for review; a review window expired
while they were away) go through `notifications.services.notify`.
"""

from __future__ import annotations

from video_pipeline.services.preferences import job_preferences

import importlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from audit.services import record_audit_event
from billing.quota import reserve_quota
from content_planning.models import ApprovalMode
from notifications.services import notify
from video_pipeline.models import JobStatus, Stage, VideoJob

logger = logging.getLogger("video_pipeline.approval")

# FR-39: restart point for "request changes" — the three stages a creator can
# ask to redo. Also the DRF ChoiceField source for RequestChangesSerializer.
RESTART_STAGES = (
    (Stage.SCRIPT, "Script"),
    (Stage.VOICE, "Voice"),
    (Stage.VISUALS, "Visuals"),
)

APPROVAL_TIMEOUT = timedelta(hours=48)  # A-3
FREE_REGENERATIONS_PER_JOB = 2  # A-21, mirrors billing.quota.FREE_REGENERATIONS_PER_JOB
PREVIEW_URL_TTL = timedelta(hours=24)  # NFR-7

_STAGE_TASK = {
    Stage.SCRIPT: "generate_script",
    Stage.VOICE: "generate_voice",
    Stage.VISUALS: "generate_visuals",
}


class JobNotAwaitingApproval(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "JOB_NOT_AWAITING_APPROVAL"
    default_detail = "This video is not awaiting your approval."


class JobNotEditable(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "JOB_NOT_EDITABLE"
    default_detail = "This video can no longer be edited."


def _enqueue_stage(job: VideoJob, stage: str) -> None:
    task_name = _STAGE_TASK[stage]
    tasks_module = importlib.import_module("video_pipeline.tasks")
    task = getattr(tasks_module, task_name)
    transaction.on_commit(lambda job_id=str(job.pk): task.apply_async(args=[job_id]))


def _enqueue_upload(job: VideoJob) -> None:
    from video_pipeline.tasks import upload_to_youtube

    transaction.on_commit(
        lambda job_id=str(job.pk): upload_to_youtube.apply_async(args=[job_id])
    )


def ensure_preview_token(job: VideoJob) -> VideoJob:
    """NFR-7: signed preview URL, 24h TTL, refreshed only once expired."""
    now = timezone.now()
    if job.preview_token and job.preview_expires_at and job.preview_expires_at > now:
        return job
    job.preview_token = secrets.token_urlsafe(32)
    job.preview_expires_at = now + PREVIEW_URL_TTL
    job.save(update_fields=["preview_token", "preview_expires_at", "updated_at"])
    return job


def preview_url(job: VideoJob) -> str:
    """NFR-7: a real time-limited object URL for the assembled video."""
    if not job.final_video_s3_key:
        # Not assembled yet — a placeholder the frontend can poll against.
        base = settings.FRONTEND_BASE_URL.rstrip("/")
        return f"{base}/preview/{job.preview_token}"
    from core.storage import get_storage

    return get_storage().signed_url(
        job.final_video_s3_key, expires_sec=int(PREVIEW_URL_TTL.total_seconds())
    )


# ---------------------------------------------------------------------------
# System-triggered: stage 6 (final moderation) -> approval/auto-publish
# ---------------------------------------------------------------------------
def on_final_moderation_passed(job: VideoJob) -> str:
    """FR-38, FR-40. Returns the job's new status."""
    from video_pipeline.models import VideoAsset, AssetKind

    asset = (
        VideoAsset.objects.filter(job=job, kind=AssetKind.FINAL_VIDEO)
        .order_by("-created_at")
        .first()
    )
    job.moderation_approved_sha256 = asset.checksum_sha256 if asset else ""
    from video_pipeline.services.moderation_proof import metadata_digest

    job.moderation_metadata_sha256 = metadata_digest(job)
    job.save(
        update_fields=[
            "moderation_approved_sha256",
            "moderation_metadata_sha256",
            "updated_at",
        ]
    )
    preference = job_preferences(job)
    auto = bool(preference and preference.approval_mode == ApprovalMode.AUTO)

    with transaction.atomic():
        if auto:
            job.status = JobStatus.UPLOAD_QUEUED
            job.save(update_fields=["status", "updated_at"])
            _enqueue_upload(job)
        else:
            ensure_preview_token(job)
            job.status = JobStatus.AWAITING_APPROVAL
            job.approval_requested_at = timezone.now()
            job.save(update_fields=["status", "approval_requested_at", "updated_at"])
        record_audit_event(
            actor_type="system",
            action="video_job.moderation_passed",
            resource_type="video_job",
            resource_id=str(job.pk),
            after={
                "status": job.status,
                "approval_mode": preference.approval_mode if preference else None,
            },
        )

    if not auto:
        notify(
            job.user,
            "video.awaiting_approval",
            job=job,
            ctx={"title": job.title, "url": preview_url(job)},
        )
    logger.info(
        "final_moderation_routed",
        extra={"job_id": str(job.pk), "status": job.status, "auto": auto},
    )
    return job.status


# ---------------------------------------------------------------------------
# Creator-triggered (FR-38..FR-41)
# ---------------------------------------------------------------------------
def _require_status(job: VideoJob, allowed: set[str]) -> None:
    if job.status not in allowed:
        raise JobNotAwaitingApproval(
            f"Job is {job.status}; expected one of {sorted(allowed)}."
        )


def approve_job(user, job: VideoJob, request=None) -> VideoJob:
    """FR-39: awaiting_approval -> approved, enqueue upload immediately.

    `approved` is deliberately a distinct status from `upload_queued` (SPEC 7.2)
    so the audit trail shows a human decision happened; `upload_to_youtube`
    accepts jobs in either status (see `video_pipeline.tasks._UPLOAD_ACCEPTED_STATUSES`).
    """
    _require_status(job, {JobStatus.AWAITING_APPROVAL})
    with transaction.atomic():
        job.status = JobStatus.APPROVED
        job.approved_at = timezone.now()
        job.approval_actor = user
        job.save(
            update_fields=["status", "approved_at", "approval_actor", "updated_at"]
        )
        _enqueue_upload(job)
        record_audit_event(
            actor_type="user",
            actor_id=user.id,
            action="video_job.approved",
            resource_type="video_job",
            resource_id=str(job.pk),
            request=request,
            after={"status": job.status},
        )
    logger.info(
        "video_job_approved", extra={"job_id": str(job.pk), "actor_id": str(user.id)}
    )
    return job


def reject_job(user, job: VideoJob, reason: str, request=None) -> VideoJob:
    """FR-39: terminal, no quota refund (SPEC 7.2 kvota qoidasi)."""
    _require_status(job, {JobStatus.AWAITING_APPROVAL})
    with transaction.atomic():
        job.status = JobStatus.REJECTED
        job.rejected_at = timezone.now()
        job.approval_actor = user
        job.rejection_reason = reason
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "rejected_at",
                "approval_actor",
                "rejection_reason",
                "completed_at",
                "updated_at",
            ]
        )
        record_audit_event(
            actor_type="user",
            actor_id=user.id,
            action="video_job.rejected",
            resource_type="video_job",
            resource_id=str(job.pk),
            request=request,
            after={"status": job.status, "reason": reason},
        )
    logger.info(
        "video_job_rejected", extra={"job_id": str(job.pk), "actor_id": str(user.id)}
    )
    return job


def request_changes(
    user, job: VideoJob, *, comment: str, restart_stage: str, request=None
) -> VideoJob:
    """FR-39, A-21: the first 2 regenerations of a job are free; the 3rd+ costs
    quota (`billing.quota.reserve_quota(kind="regeneration")`).
    """
    _require_status(job, {JobStatus.AWAITING_APPROVAL})
    if restart_stage not in _STAGE_TASK:
        raise JobNotEditable(f"Unknown restart_stage {restart_stage!r}.")

    with transaction.atomic():
        if job.regeneration_count >= FREE_REGENERATIONS_PER_JOB:
            reserve_quota(user, kind="regeneration", job=job)

        meta = dict(job.script_meta or {})
        history = list(meta.get("change_requests") or [])
        history.append(
            {
                "at": timezone.now().isoformat(),
                "by": str(user.id),
                "comment": comment,
                "restart_stage": restart_stage,
                "regeneration_index": job.regeneration_count + 1,
            }
        )
        meta["change_requests"] = history
        job.script_meta = meta
        job.regeneration_count += 1
        job.status = JobStatus.CHANGES_REQUESTED
        job.approval_requested_at = None
        job.save(
            update_fields=[
                "script_meta",
                "regeneration_count",
                "status",
                "approval_requested_at",
                "updated_at",
            ]
        )
        _enqueue_stage(job, restart_stage)
        record_audit_event(
            actor_type="user",
            actor_id=user.id,
            action="video_job.changes_requested",
            resource_type="video_job",
            resource_id=str(job.pk),
            request=request,
            after={
                "restart_stage": restart_stage,
                "regeneration_count": job.regeneration_count,
            },
        )
    logger.info(
        "video_job_changes_requested",
        extra={
            "job_id": str(job.pk),
            "restart_stage": restart_stage,
            "regeneration_count": job.regeneration_count,
        },
    )
    return job


@transaction.atomic
def update_metadata(user, job: VideoJob, data: dict, request=None) -> VideoJob:
    """FR-41: title/description/tags are editable up to the approval decision."""
    _require_status(job, {JobStatus.AWAITING_APPROVAL, JobStatus.CHANGES_REQUESTED})
    before = {"title": job.title, "description": job.description, "tags": job.tags}
    fields = [f for f in ("title", "description", "tags") if f in data]
    if not fields:
        return job
    for field in fields:
        setattr(job, field, data[field])
    if job.final_video_s3_key:
        from video_pipeline.tasks import moderate_content

        job.moderation_approved_sha256 = ""
        job.moderation_metadata_sha256 = ""
        job.status = JobStatus.MODERATING_SCRIPT
        fields.extend(
            ["moderation_approved_sha256", "moderation_metadata_sha256", "status"]
        )
        transaction.on_commit(
            lambda: moderate_content.apply_async(
                args=[str(job.pk)], kwargs={"scope": "script"}
            )
        )
    job.save(update_fields=[*fields, "updated_at"])
    record_audit_event(
        actor_type="user",
        actor_id=user.id,
        action="video_job.metadata_updated",
        resource_type="video_job",
        resource_id=str(job.pk),
        request=request,
        before=before,
        after={"title": job.title, "description": job.description, "tags": job.tags},
    )
    logger.info(
        "video_job_metadata_updated", extra={"job_id": str(job.pk), "fields": fields}
    )
    return job


# ---------------------------------------------------------------------------
# FR-38 timeout sweep
# ---------------------------------------------------------------------------
def expire_stale_approvals(*, now=None) -> dict:
    """Jobs stuck in `awaiting_approval` past the 48h window (A-3): auto-publish
    when the preference opts in, else `expired` (no quota refund, SPEC 7.2).
    """
    now = now or timezone.now()
    cutoff = now - APPROVAL_TIMEOUT
    stale = list(
        VideoJob.objects.select_related("preference", "user").filter(
            status=JobStatus.AWAITING_APPROVAL, approval_requested_at__lte=cutoff
        )
    )
    published = expired = 0
    for job in stale:
        auto_publish = bool(job.preference and job.preference.auto_publish_on_timeout)
        with transaction.atomic():
            if auto_publish:
                job.status = JobStatus.UPLOAD_QUEUED
                job.save(update_fields=["status", "updated_at"])
                _enqueue_upload(job)
                action, published = "video_job.auto_published_on_timeout", published + 1
            else:
                job.status = JobStatus.EXPIRED
                job.completed_at = now
                job.save(update_fields=["status", "completed_at", "updated_at"])
                action, expired = "video_job.expired", expired + 1
            record_audit_event(
                actor_type="system",
                action=action,
                resource_type="video_job",
                resource_id=str(job.pk),
                after={"status": job.status},
            )
        try:
            notify(
                job.user,
                "video.auto_published_on_timeout" if auto_publish else "video.expired",
                job=job,
                ctx={"title": job.title},
            )
        except Exception:  # noqa: BLE001 — a notification failure must not break the sweep
            logger.exception(
                "expire_stale_approvals_notify_failed", extra={"job_id": str(job.pk)}
            )
    if published or expired:
        logger.info(
            "expire_stale_approvals_completed",
            extra={"published": published, "expired": expired},
        )
    return {"published": published, "expired": expired}
