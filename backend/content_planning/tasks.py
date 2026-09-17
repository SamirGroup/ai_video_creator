"""Celery Beat scheduler (FR-35, FR-36, ARCHITECTURE 4.4).

* `materialise_scheduled_jobs` (every 15 min): for every active, unpaused
  preference whose creator passes the generation gates (subscription usable,
  contract signed, payment method saved) and whose channel is connected,
  compute the next publish slot; if it is within the lead time (24h) and no
  job exists for it, create `VideoJob(status=scheduled)`. One pending
  scheduled job per preference at a time, so a re-run never duplicates.
* `enqueue_due_jobs` (every 5 min): `scheduled` jobs whose generation must
  start now (`scheduled_for - expected pipeline duration`) are re-gated,
  get their quota reserved, move to `queued` and `generate_script` is sent
  to `q_script`.

Both tasks are idempotent and safe to run concurrently (row locks with
`skip_locked`). Schedules are seeded into django-celery-beat by
`content_planning/migrations/0002_seed_beat_schedule.py` (D-7).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from audit.services import record_audit_event
from billing.quota import QuotaExceeded, remaining, reserve_quota
from channels.models import ConnectionStatus
from content_planning.models import ContentPreference
from content_planning.services import generation_start_for, next_publish_slot
from contracts.gates import check_generation_eligibility
from notifications.services import notify

logger = logging.getLogger("content_planning.tasks")

_BLOCK_MESSAGES = {
    "CONTRACT_NOT_SIGNED": (
        "Please sign the creator agreement",
        "Scheduled video generation is on hold until you sign the current creator agreement in your dashboard.",
    ),
    "PAYMENT_METHOD_REQUIRED": (
        "Please add a payment method",
        "Scheduled video generation is on hold until you save a payment method in your dashboard.",
    ),
    "SUBSCRIPTION_INACTIVE": (
        "Your subscription needs attention",
        "Scheduled video generation is on hold because your subscription is not active.",
    ),
}


def _notify_once(user, key: str, type_: str, ctx: dict) -> None:
    """Send at most one notification per `key` per SCHEDULER_NOTIFY_DEDUPE_SEC (AC-3)."""
    cache_key = f"scheduler:notify:{user.id}:{key}"
    if cache.add(cache_key, "1", timeout=settings.SCHEDULER_NOTIFY_DEDUPE_SEC):
        notify(user, type_, ctx=ctx)


def _notify_blocked(user, code: str) -> None:
    subject, message = _BLOCK_MESSAGES.get(
        code, ("Video generation is on hold", "Please check your dashboard.")
    )
    _notify_once(
        user, code, "generation.blocked", {"subject": subject, "message": message}
    )


def _notify_quota_exhausted(user, quota) -> None:
    from billing.models import UsageCounter

    counter = UsageCounter.objects.filter(
        user=user, period_start=quota.period_start
    ).first()
    if counter is None or counter.exhausted_notified_at is not None:
        return
    counter.exhausted_notified_at = timezone.now()
    counter.save(update_fields=["exhausted_notified_at", "updated_at"])
    notify(
        user,
        "quota.exhausted",
        ctx={
            "subject": "Monthly video quota reached",
            "message": (
                f"You have used {quota.videos_used} of {quota.videos_quota} videos for this billing period. "
                f"{quota.upgrade_hint}"
            ),
        },
    )


def _channel_ok(channel) -> bool:
    return channel.deleted_at is None and channel.status == ConnectionStatus.CONNECTED


@shared_task(name="content_planning.tasks.materialise_scheduled_jobs")
def materialise_scheduled_jobs() -> dict:
    from video_pipeline.models import JobStatus, JobTrigger, VideoJob

    now = timezone.now()
    lead = timedelta(hours=settings.SCHEDULER_LEAD_TIME_HOURS)
    created = skipped = 0

    prefs = (
        ContentPreference.objects.filter(
            is_paused=False, automatic_schedule_enabled=True, deleted_at__isnull=True
        )
        .select_related("channel", "user")
        .order_by("created_at")
    )
    for pref in prefs.iterator():
        user = pref.user
        if not _channel_ok(pref.channel):
            skipped += 1
            continue
        eligibility = check_generation_eligibility(user)
        if not eligibility.allowed:
            _notify_blocked(user, eligibility.code)
            skipped += 1
            continue
        if VideoJob.objects.filter(
            preference=pref, status=JobStatus.SCHEDULED
        ).exists():
            skipped += 1
            continue
        quota = remaining(user)
        if quota.videos_remaining <= 0:
            _notify_quota_exhausted(user, quota)
            skipped += 1
            continue

        try:
            slot = next_publish_slot(pref, now)
        except (ValueError, KeyError) as exc:
            logger.warning(
                "scheduler_slot_error",
                extra={"preference_id": str(pref.id), "error": str(exc)},
            )
            skipped += 1
            continue
        if slot - now > lead:
            skipped += 1
            continue
        if VideoJob.objects.filter(preference=pref, scheduled_for=slot).exists():
            skipped += 1
            continue

        with transaction.atomic():
            job = VideoJob.objects.create(
                user=user,
                channel=pref.channel,
                preference=pref,
                trigger=JobTrigger.SCHEDULED,
                status=JobStatus.SCHEDULED,
                scheduled_for=slot,
                language=pref.language,
                duration_sec=pref.video_duration_sec,
            )
            record_audit_event(
                actor_type="system",
                action="video_job.scheduled",
                resource_type="video_job",
                resource_id=str(job.id),
                after={
                    "scheduled_for": slot.isoformat(),
                    "preference_id": str(pref.id),
                },
            )
        created += 1
        logger.info(
            "scheduler_job_materialised",
            extra={"job_id": str(job.id), "scheduled_for": slot.isoformat()},
        )

    return {"created": created, "skipped": skipped}


def _enqueue_script_stage(job_id: str) -> None:
    from video_pipeline.tasks import generate_script

    generate_script.apply_async(args=[job_id], queue="q_script")


@shared_task(name="content_planning.tasks.enqueue_due_jobs")
def enqueue_due_jobs() -> dict:
    from video_pipeline.models import JobStatus, VideoJob

    now = timezone.now()
    stale_before = now - timedelta(hours=settings.SCHEDULER_STALE_AFTER_HOURS)
    due_cutoff = now + timedelta(minutes=settings.PIPELINE_EXPECTED_DURATION_MINUTES)
    enqueued = held = canceled = 0

    due_ids = list(
        VideoJob.objects.filter(
            status=JobStatus.SCHEDULED, scheduled_for__lte=due_cutoff
        )
        .order_by("scheduled_for")
        .values_list("id", flat=True)
    )
    for job_id in due_ids:
        with transaction.atomic():
            job = (
                VideoJob.objects.select_for_update(skip_locked=True)
                .select_related("user", "channel", "preference")
                .filter(id=job_id, status=JobStatus.SCHEDULED)
                .first()
            )
            if job is None:
                continue  # another worker took it, or it was canceled meanwhile

            if job.scheduled_for < stale_before:
                job.status = JobStatus.CANCELED
                job.error_code = "stale_schedule"
                job.error_message = (
                    "Scheduled slot passed while generation was on hold."
                )
                job.completed_at = now
                job.save(
                    update_fields=[
                        "status",
                        "error_code",
                        "error_message",
                        "completed_at",
                        "updated_at",
                    ]
                )
                record_audit_event(
                    actor_type="system",
                    action="video_job.canceled",
                    resource_type="video_job",
                    resource_id=str(job.id),
                    after={"status": job.status, "reason": "stale_schedule"},
                )
                canceled += 1
                continue

            pref = job.preference
            if pref is not None and (pref.is_paused or pref.deleted_at is not None):
                held += 1
                continue
            if not _channel_ok(job.channel):
                held += 1
                continue
            eligibility = check_generation_eligibility(job.user)
            if not eligibility.allowed:
                _notify_blocked(job.user, eligibility.code)
                held += 1
                continue
            if generation_start_for(job.scheduled_for) > now:
                held += 1
                continue

            try:
                reserve_quota(job.user, kind="video", job=job)
            except QuotaExceeded as exc:
                _notify_quota_exhausted(job.user, exc.quota)
                held += 1
                continue
            except Exception as exc:  # concurrent-jobs cap: try again next run
                logger.info(
                    "scheduler_enqueue_deferred",
                    extra={"job_id": str(job.id), "reason": str(exc)},
                )
                held += 1
                continue

            job.status = JobStatus.QUEUED
            job.save(update_fields=["status", "updated_at"])
            record_audit_event(
                actor_type="system",
                action="video_job.queued",
                resource_type="video_job",
                resource_id=str(job.id),
                after={
                    "status": job.status,
                    "scheduled_for": job.scheduled_for.isoformat(),
                },
            )
            transaction.on_commit(lambda jid=str(job.id): _enqueue_script_stage(jid))
        enqueued += 1
        logger.info("scheduler_job_enqueued", extra={"job_id": str(job_id)})

    return {"enqueued": enqueued, "held": held, "canceled": canceled}


@shared_task(name="content_planning.tasks.prepare_content_plan", acks_late=True)
def prepare_content_plan(plan_id):
    from content_planning.proposals import prepare_proposal

    return prepare_proposal(plan_id)
