"""Moderator decision on a flagged/blocked job (FR-48, FR-81).

`video_jobs.status = moderation_review` can be reached from two different
gates (SPEC 7.1 #2 script, #6 final) — which one is recorded on the latest
`moderation_logs` row for the job. An `approved` decision resumes the
pipeline from wherever that gate stopped it:

* stage=script  -> stage 3 (voice), same hand-off `moderate_content` uses on
  an unflagged pass.
* stage=final   -> `video_pipeline.services.approval.on_final_moderation_passed`
  (review_required -> `awaiting_approval`, auto -> straight to upload).

A `rejected` decision is terminal (`moderation_rejected`) either way — never
auto-published (FR-48).
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from audit.services import record_audit_event
from moderation.models import ModerationLog, ModerationStage, ReviewDecision
from notifications.services import notify
from video_pipeline.models import JobStatus, VideoJob

logger = logging.getLogger("moderation.services")


class JobNotInModerationReview(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "JOB_NOT_IN_MODERATION_REVIEW"
    default_detail = "This video is not in the moderation queue."


def moderation_queue(*, stage: str | None = None) -> QuerySet[VideoJob]:
    qs = VideoJob.objects.filter(status=JobStatus.MODERATION_REVIEW).select_related("user", "channel")
    if stage:
        qs = qs.filter(moderation_logs__stage=stage).distinct()
    return qs.order_by("-updated_at")


def _latest_log(job: VideoJob) -> ModerationLog | None:
    return job.moderation_logs.order_by("-created_at").first()


def decide(staff_user, job: VideoJob, *, decision: str, reason: str, request=None) -> VideoJob:
    if job.status != JobStatus.MODERATION_REVIEW:
        raise JobNotInModerationReview(f"Job is {job.status}, not moderation_review.")

    log = _latest_log(job)
    review_decision = ReviewDecision.APPROVED if decision == "approved" else ReviewDecision.REJECTED
    stage = log.stage if log else ModerationStage.FINAL

    with transaction.atomic():
        if log is not None:
            ModerationLog.objects.filter(pk=log.pk).update(
                reviewed_by=staff_user,
                review_decision=review_decision,
                review_reason=reason,
                reviewed_at=timezone.now(),
            )

        if decision == "rejected":
            job.status = JobStatus.MODERATION_REJECTED
            job.rejection_reason = reason
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "rejection_reason", "completed_at", "updated_at"])
            new_status = job.status
        elif stage == ModerationStage.SCRIPT:
            from video_pipeline.tasks import generate_voice

            job.status = JobStatus.SCRIPT_READY
            job.save(update_fields=["status", "updated_at"])
            transaction.on_commit(lambda job_id=str(job.pk): generate_voice.apply_async(args=[job_id]))
            new_status = job.status
        else:
            from video_pipeline.services.approval import on_final_moderation_passed

            new_status = on_final_moderation_passed(job)

        record_audit_event(
            actor_type="staff",
            actor_id=staff_user.id,
            action="moderation.decided",
            resource_type="video_job",
            resource_id=str(job.pk),
            request=request,
            after={"decision": decision, "reason": reason, "status": new_status, "gate_stage": stage},
        )

    if decision == "rejected":
        notify(job.user, "video.moderation_rejected", job=job, ctx={"title": job.title, "reason": reason})

    logger.info(
        "moderation_decided",
        extra={"job_id": str(job.pk), "decision": decision, "status": new_status, "staff_id": str(staff_user.id)},
    )
    return job
