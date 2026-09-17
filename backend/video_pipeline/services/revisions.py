"""Correct content, never reuse an approval. Stop on hard blocks, quotas or budget limits."""

from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from audit.services import record_audit_event
from billing.quota import reserve_quota
from contracts.gates import assert_generation_allowed
from video_pipeline.models import VideoJob, VideoRevision, JobStatus, JobTrigger


@transaction.atomic
def request_revision(job, *, reason, findings=None):
    root = job
    while root.parent_job_id:
        root = root.parent_job
    root = VideoJob.objects.select_for_update().get(pk=root.pk)
    current = VideoJob.objects.select_for_update().get(pk=job.pk)
    existing = VideoRevision.objects.filter(previous_job=current).first()
    if existing:
        return existing.replacement_job
    if current.status not in (
        JobStatus.MODERATION_REVIEW,
        JobStatus.MODERATION_REJECTED,
    ):
        raise ValidationError("Only a moderation-held video can be revised.")
    number = root.revision_history.count() + 1
    if number > int(getattr(settings, "MAX_MODERATION_REVISIONS", 3)):
        raise ValidationError(
            "Automatic revision limit reached. Manual review is required."
        )
    spent = root.total_cost_usd + (
        VideoJob.objects.filter(revision_origin__root_job=root).aggregate(
            value=Sum("total_cost_usd")
        )["value"]
        or Decimal("0")
    )
    ceiling = Decimal(str(getattr(settings, "MODERATION_REVISION_BUDGET_USD", "30")))
    if ceiling <= 0 or spent >= ceiling:
        raise ValidationError("Revision budget reached. Manual review is required.")
    assert_generation_allowed(current.user)
    context = dict(current.generation_context or {})
    context["moderation_feedback"] = {
        "reason": reason[:4000],
        "findings": findings or {},
        "instruction": "Remove the problematic material and underlying unsafe premise. Develop an original compliant alternative. Do not disguise, paraphrase or evade the moderation finding. The replacement must pass independent moderation from the start.",
    }
    child = VideoJob.objects.create(
        user=current.user,
        channel=current.channel,
        preference=current.preference,
        parent_job=current,
        trigger=JobTrigger.REGENERATION,
        status=JobStatus.QUEUED,
        scheduled_for=current.scheduled_for,
        language=current.language,
        duration_sec=current.duration_sec,
        generation_context=context,
        regeneration_count=number,
    )
    reserve_quota(current.user, kind="video", job=child)
    VideoRevision.objects.create(
        previous_job=current,
        replacement_job=child,
        root_job=root,
        number=number,
        reason=reason,
        findings=findings or {},
    )
    current.status = JobStatus.MODERATION_REJECTED
    current.completed_at = timezone.now()
    current.rejection_reason = reason
    current.save(
        update_fields=["status", "completed_at", "rejection_reason", "updated_at"]
    )
    from video_pipeline.tasks import generate_script

    transaction.on_commit(
        lambda: generate_script.apply_async(
            args=[str(child.pk)], queue="q_script", countdown=60
        )
    )
    record_audit_event(
        actor_type="system",
        action="video.revision_created",
        resource_type="video_job",
        resource_id=str(current.pk),
        after={
            "replacement_job_id": str(child.pk),
            "revision": number,
            "reason": reason,
        },
    )
    return child


def maybe_auto_revise(job, outcome):
    """Hard blocks always stay in human review. Flags can be corrected within explicit limits."""
    if outcome.verdict != "flag" or not getattr(
        settings, "AUTO_MODERATION_REVISIONS", True
    ):
        return None
    if job.preference is None or job.preference.is_paused:
        return None
    try:
        child = request_revision(
            job,
            reason=job.error_message,
            findings={
                "category": outcome.max_category,
                "scores": outcome.category_scores,
            },
        )
        job.refresh_from_db()
        return child
    except APIException:
        # Quota/contract/budget guards leave the original in the review queue.
        return None
