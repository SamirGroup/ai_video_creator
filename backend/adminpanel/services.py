"""Admin panel business logic (FR-79, FR-80, FR-83, FR-84, FR-85).

Views stay thin; every write and audit-log entry lives here, matching the
convention used by `content_planning.services`, `video_pipeline.services.approval`
and `moderation.services`.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from accounts.models import Role, User, UserRole, UserStatus
from audit.services import record_audit_event
from providers.models import ApiCredentialConfig

logger = logging.getLogger("adminpanel.services")


class JobNotRetryable(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "JOB_NOT_RETRYABLE"
    default_detail = "Only a failed job can be retried."


class SecretNotResolvable(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "SECRET_NOT_RESOLVABLE"
    default_detail = "The given secret_ref does not resolve to a configured value."


# ---------------------------------------------------------------------------
# Users (FR-79)
# ---------------------------------------------------------------------------
def suspend_user(staff_user, user: User, request=None) -> User:
    user.status = UserStatus.SUSPENDED
    user.save(update_fields=["status", "updated_at"])
    record_audit_event(
        actor_type="staff",
        actor_id=staff_user.id,
        action="admin.user_suspended",
        resource_type="user",
        resource_id=str(user.id),
        request=request,
    )
    logger.info("admin_user_suspended", extra={"user_id": str(user.id), "staff_id": str(staff_user.id)})
    return user


def reactivate_user(staff_user, user: User, request=None) -> User:
    user.status = UserStatus.ACTIVE
    user.save(update_fields=["status", "updated_at"])
    record_audit_event(
        actor_type="staff",
        actor_id=staff_user.id,
        action="admin.user_reactivated",
        resource_type="user",
        resource_id=str(user.id),
        request=request,
    )
    logger.info("admin_user_reactivated", extra={"user_id": str(user.id), "staff_id": str(staff_user.id)})
    return user


def set_roles(staff_user, user: User, role_codes: list[str], request=None) -> User:
    """Replaces the user's full role set (validated by `SetRolesSerializer`)."""
    with transaction.atomic():
        before = list(user.user_roles.values_list("role__code", flat=True))
        user.user_roles.all().delete()
        for code in role_codes:
            UserRole.objects.create(user=user, role=Role.objects.get(code=code), granted_by=staff_user)
        record_audit_event(
            actor_type="staff",
            actor_id=staff_user.id,
            action="admin.roles_changed",
            resource_type="user",
            resource_id=str(user.id),
            request=request,
            before={"roles": before},
            after={"roles": role_codes},
        )
    return user


def view_user(staff_user, user: User, request=None) -> None:
    """FR-88: every staff view of a user's detail is itself audited (Limited Use)."""
    record_audit_event(
        actor_type="staff",
        actor_id=staff_user.id,
        action="staff.viewed_user",
        resource_type="user",
        resource_id=str(user.id),
        request=request,
    )


# ---------------------------------------------------------------------------
# Video jobs (FR-80)
# ---------------------------------------------------------------------------
def retry_job(staff_user, job, request=None):
    from video_pipeline.models import JobStatus, Stage
    from video_pipeline.tasks import assemble_video, generate_script, generate_visuals, generate_voice

    if job.status != JobStatus.FAILED:
        raise JobNotRetryable(f"Job is {job.status}, not failed.")

    stage_task = {
        Stage.SCRIPT: generate_script,
        Stage.VOICE: generate_voice,
        Stage.VISUALS: generate_visuals,
        Stage.ASSEMBLY: assemble_video,
    }
    task = stage_task.get(job.current_stage, generate_script)

    job.status = JobStatus.QUEUED
    job.error_code = ""
    job.error_message = ""
    job.save(update_fields=["status", "error_code", "error_message", "updated_at"])
    transaction.on_commit(lambda job_id=str(job.pk): task.apply_async(args=[job_id]))
    record_audit_event(
        actor_type="staff",
        actor_id=staff_user.id,
        action="admin.job_retried",
        resource_type="video_job",
        resource_id=str(job.pk),
        request=request,
        after={"restart_stage": job.current_stage},
    )
    logger.info("admin_job_retried", extra={"job_id": str(job.pk), "stage": job.current_stage})
    return job


def cancel_job(staff_user, job, request=None):
    from billing.quota import release_quota
    from content_planning.services import JobNotCancelable
    from video_pipeline.models import JobStatus

    if job.is_terminal() or job.status in (JobStatus.UPLOADING, JobStatus.UPLOADED):
        raise JobNotCancelable(f"Job is {job.status} and cannot be canceled.")

    quota_refunded = False
    with transaction.atomic():
        if job.started_at is None:
            quota_refunded = release_quota(job.user, job) is not None
        job.status = JobStatus.CANCELED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at", "updated_at"])
        record_audit_event(
            actor_type="staff",
            actor_id=staff_user.id,
            action="admin.job_canceled",
            resource_type="video_job",
            resource_id=str(job.pk),
            request=request,
            after={"status": job.status, "quota_refunded": quota_refunded},
        )
    logger.info("admin_job_canceled", extra={"job_id": str(job.pk), "quota_refunded": quota_refunded})
    return job


# ---------------------------------------------------------------------------
# Config (FR-83, FR-84)
# ---------------------------------------------------------------------------
def rotate_secret(staff_user, config: ApiCredentialConfig, secret_ref: str, request=None) -> ApiCredentialConfig:
    old_ref = config.secret_ref
    config.secret_ref = secret_ref
    if not config.has_secret():
        config.secret_ref = old_ref
        raise SecretNotResolvable(f"{secret_ref!r} does not resolve to a configured value.")
    config.save(update_fields=["secret_ref", "updated_at"])
    # Never log the resolved value (NFR-3) — only that a rotation happened and to which name.
    record_audit_event(
        actor_type="staff",
        actor_id=staff_user.id,
        action="admin.provider_secret_rotated",
        resource_type="api_credentials_config",
        resource_id=str(config.id),
        request=request,
        after={"secret_ref": secret_ref},
    )
    return config


# ---------------------------------------------------------------------------
# System health (FR-85)
# ---------------------------------------------------------------------------
def queue_depth_by_status() -> dict[str, int]:
    """Best-effort proxy for FR-85 "navbat uzunligi": counts of non-terminal
    jobs grouped by their pipeline status. A live Celery `inspect()` call is
    deliberately not used — its availability depends on a reachable
    broker/worker, which would make this endpoint's own availability depend
    on infra orthogonal to the DB-backed data it otherwise reports (NFR-28).
    """
    from django.db.models import Count

    from video_pipeline.models import JobStatus, VideoJob

    rows = (
        VideoJob.objects.exclude(status__in=list(JobStatus.terminal_statuses()))
        .values("status")
        .annotate(count=Count("id"))
    )
    return {row["status"]: row["count"] for row in rows}


def system_health() -> dict:
    from providers.models import ApiUsageLog

    since = timezone.now() - timedelta(hours=24)
    usage = ApiUsageLog.objects.filter(created_at__gte=since)
    total = usage.count()
    failed = usage.filter(success=False).count()
    return {
        "queue_depth_by_status": queue_depth_by_status(),
        "provider_calls_24h": total,
        "provider_failures_24h": failed,
        "provider_error_rate_24h": round(failed / total, 4) if total else 0.0,
    }
