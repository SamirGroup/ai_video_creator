"""Plan quota enforcement (FR-21..FR-24, SPEC 5.7 `usage_counters`, AC-3).

Public interface (other tracks call these — keep the signatures stable):

    reserve_quota(user, *, kind="video", job=None) -> UsageCounter
        Consumes one unit for the current billing period. Raises
        `QuotaExceeded` (HTTP 402, code QUOTA_EXCEEDED) when the plan quota is
        used up, or `ConcurrentJobsLimitExceeded` (HTTP 409,
        code CONCURRENT_JOBS_LIMIT) when the plan's parallel-job cap is hit.
        `kind="regeneration"` uses the A-21 rule: the first two regenerations
        of a job are free (only `regenerations_used` increments), further ones
        count as a video. Idempotent per `job` — reserving twice for the same
        job is a no-op.

    release_quota(user, job) -> UsageCounter | None
        Gives the unit back (SPEC 7.2: on `failed` or on `canceled` before
        generation started). Idempotent — releasing a job that holds no
        reservation is a no-op.

    remaining(user) -> QuotaStatus
        Snapshot used by the API and the scheduler gate.

    assert_can_generate(user, *, kind="video") -> QuotaStatus
        Read-only pre-check with the same exceptions as `reserve_quota`.

Quota is keyed by `subscription.current_period_start` so it resets on the
subscription boundary (FR-24). Creators without a subscription row (or whose
Stripe period is not synced yet) get the Free plan (A-20: 2 videos, 60 s) on a
calendar-month window.
"""
from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from billing.models import Plan, Subscription, SubscriptionStatus, UsageCounter

logger = logging.getLogger("billing.quota")

FREE_PLAN_CODE = "free"
# A-20 fallback used only when no `plans` row with code "free" exists yet.
FREE_PLAN_DEFAULTS = {
    "code": FREE_PLAN_CODE,
    "videos_per_period": 2,
    "max_video_duration_sec": 60,
    "concurrent_jobs": 1,
}
FREE_REGENERATIONS_PER_JOB = 2  # A-21
# Subscriptions in these states grant their plan's quota; anything else drops
# to the Free plan (FR-26: `past_due`/`suspended` stop generation).
QUOTA_GRANTING_STATUSES = {SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE}

# Statuses that occupy a worker slot for the `concurrent_jobs` limit. Terminal
# statuses, `draft`/`scheduled` (not started) and creator-side waits
# (`awaiting_approval`, `changes_requested`, `approved`) do not count.
IN_FLIGHT_STATUSES = (
    "queued",
    "generating_script",
    "script_ready",
    "moderating_script",
    "generating_voice",
    "voice_ready",
    "generating_visuals",
    "visuals_ready",
    "assembling",
    "assembled",
    "moderating_final",
    "moderation_review",
    "retrying",
    "upload_queued",
    "uploading",
)


class QuotaExceeded(APIException):
    """FR-23: no new job when the period quota is used up; response carries an upgrade hint."""

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_code = "QUOTA_EXCEEDED"
    default_detail = "Your plan's video quota for this billing period is used up. Upgrade your plan to continue."

    def __init__(self, detail=None, *, quota: QuotaStatus | None = None):
        super().__init__(detail)
        self.quota = quota


class ConcurrentJobsLimitExceeded(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "CONCURRENT_JOBS_LIMIT"
    default_detail = "Your plan's limit of concurrently running video jobs is reached. Wait for a job to finish or upgrade."

    def __init__(self, detail=None, *, quota: QuotaStatus | None = None):
        super().__init__(detail)
        self.quota = quota


@dataclass(frozen=True)
class PlanLimits:
    code: str
    videos_per_period: int
    max_video_duration_sec: int
    concurrent_jobs: int


@dataclass(frozen=True)
class QuotaStatus:
    plan_code: str
    period_start: datetime
    period_end: datetime
    videos_quota: int
    videos_used: int
    videos_remaining: int
    regenerations_used: int
    concurrent_jobs_limit: int
    concurrent_jobs_active: int
    max_video_duration_sec: int
    upgrade_hint: str

    def as_dict(self) -> dict:
        return {
            "plan_code": self.plan_code,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "videos_quota": self.videos_quota,
            "videos_used": self.videos_used,
            "videos_remaining": self.videos_remaining,
            "regenerations_used": self.regenerations_used,
            "concurrent_jobs_limit": self.concurrent_jobs_limit,
            "concurrent_jobs_active": self.concurrent_jobs_active,
            "max_video_duration_sec": self.max_video_duration_sec,
            "upgrade_hint": self.upgrade_hint,
        }


# ---------------------------------------------------------------------------
# Plan / period resolution
# ---------------------------------------------------------------------------
def _free_plan_limits() -> PlanLimits:
    plan = Plan.objects.filter(code=FREE_PLAN_CODE).first()
    if plan is not None:
        return PlanLimits(plan.code, plan.videos_per_period, plan.max_video_duration_sec, plan.concurrent_jobs)
    return PlanLimits(**FREE_PLAN_DEFAULTS)


def get_active_subscription(user) -> Subscription | None:
    """Subscription that currently grants quota, or None (Free plan applies)."""
    subscription = Subscription.objects.filter(user=user).select_related("plan").first()
    if subscription is None or subscription.status not in QUOTA_GRANTING_STATUSES:
        return None
    return subscription


def plan_limits_for(user) -> PlanLimits:
    subscription = get_active_subscription(user)
    if subscription is None:
        return _free_plan_limits()
    plan = subscription.plan
    return PlanLimits(plan.code, plan.videos_per_period, plan.max_video_duration_sec, plan.concurrent_jobs)


def _calendar_month_window(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days = calendar.monthrange(start.year, start.month)[1]
    return start, start + timedelta(days=days)


def current_period(user, *, now: datetime | None = None) -> tuple[Subscription | None, datetime, datetime]:
    """(subscription or None, period_start, period_end) for `user` right now."""
    now = now or timezone.now()
    subscription = get_active_subscription(user)
    if (
        subscription is not None
        and subscription.current_period_start
        and subscription.current_period_end
        and subscription.current_period_start <= now < subscription.current_period_end
    ):
        return subscription, subscription.current_period_start, subscription.current_period_end
    start, end = _calendar_month_window(now.astimezone(dt_timezone.utc))
    return subscription, start, end


def _upgrade_hint(plan_code: str) -> str:
    if plan_code == FREE_PLAN_CODE:
        return "Upgrade to Starter for more videos per month and longer videos."
    if plan_code == "starter":
        return "Upgrade to Professional for a larger monthly quota."
    if plan_code == "professional":
        return "Contact us about the Enterprise plan for higher limits."
    return "Upgrade your plan to raise this limit."


def _get_or_create_counter(user, *, for_update: bool = False) -> tuple[UsageCounter, PlanLimits]:
    subscription, start, end = current_period(user)
    limits = plan_limits_for(user)
    qs = UsageCounter.objects.select_for_update() if for_update else UsageCounter.objects
    counter = qs.filter(user=user, period_start=start).first()
    if counter is None:
        counter, _ = UsageCounter.objects.get_or_create(
            user=user,
            period_start=start,
            defaults={
                "subscription": subscription,
                "period_end": end,
                "videos_quota": limits.videos_per_period,
            },
        )
        if for_update:
            counter = UsageCounter.objects.select_for_update().get(pk=counter.pk)
    # Plan changes mid-period (FR-27 upgrade is immediate) must raise the cap.
    changed = []
    if counter.videos_quota != limits.videos_per_period:
        counter.videos_quota = limits.videos_per_period
        changed.append("videos_quota")
    if counter.subscription_id != (subscription.id if subscription else None):
        counter.subscription = subscription
        changed.append("subscription")
    if counter.period_end != end:
        counter.period_end = end
        changed.append("period_end")
    if changed:
        counter.save(update_fields=changed + ["updated_at"])
    return counter, limits


def _active_job_count(user) -> int:
    from video_pipeline.models import VideoJob

    return VideoJob.objects.filter(user=user, status__in=IN_FLIGHT_STATUSES).count()


def _status(counter: UsageCounter, limits: PlanLimits, user) -> QuotaStatus:
    return QuotaStatus(
        plan_code=limits.code,
        period_start=counter.period_start,
        period_end=counter.period_end,
        videos_quota=counter.videos_quota,
        videos_used=counter.videos_generated,
        videos_remaining=counter.videos_remaining,
        regenerations_used=counter.regenerations_used,
        concurrent_jobs_limit=limits.concurrent_jobs,
        concurrent_jobs_active=_active_job_count(user),
        max_video_duration_sec=limits.max_video_duration_sec,
        upgrade_hint=_upgrade_hint(limits.code),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def remaining(user) -> QuotaStatus:
    with transaction.atomic():
        counter, limits = _get_or_create_counter(user)
    return _status(counter, limits, user)


def _counts_as_video(kind: str, job) -> bool:
    if kind == "video":
        return True
    if kind == "regeneration":
        used = getattr(job, "regeneration_count", 0) if job is not None else 0
        return used >= FREE_REGENERATIONS_PER_JOB
    raise ValueError(f"Unknown quota kind: {kind!r}")


def _check(status_: QuotaStatus, *, kind: str, job, check_concurrency: bool) -> None:
    if _counts_as_video(kind, job) and status_.videos_remaining <= 0:
        raise QuotaExceeded(
            f"You have used {status_.videos_used} of {status_.videos_quota} videos in this billing period. "
            f"{status_.upgrade_hint}",
            quota=status_,
        )
    if check_concurrency and status_.concurrent_jobs_active >= status_.concurrent_jobs_limit:
        raise ConcurrentJobsLimitExceeded(
            f"{status_.concurrent_jobs_active} job(s) already running; your plan allows "
            f"{status_.concurrent_jobs_limit}. {status_.upgrade_hint}",
            quota=status_,
        )


def assert_can_generate(user, *, kind: str = "video", check_concurrency: bool = True) -> QuotaStatus:
    """Read-only guard. Raises QuotaExceeded (402) / ConcurrentJobsLimitExceeded (409)."""
    status_ = remaining(user)
    _check(status_, kind=kind, job=None, check_concurrency=check_concurrency)
    return status_


def reserve_quota(user, *, kind: str = "video", job=None, check_concurrency: bool = True) -> UsageCounter:
    """Consume one unit for the current period (call when a job enters `queued`).

    Row-locked, so two concurrent "Generate now" clicks cannot both squeeze
    through the last unit. Idempotent per `job`.
    """
    job_key = str(job.pk) if job is not None else None
    with transaction.atomic():
        counter, limits = _get_or_create_counter(user, for_update=True)
        if job_key and job_key in (counter.reserved_job_ids or []):
            return counter
        status_ = _status(counter, limits, user)
        # The job being reserved may already be `queued` (created inside the
        # same transaction); do not count it against itself.
        if job is not None and getattr(job, "status", None) in IN_FLIGHT_STATUSES:
            status_ = QuotaStatus(**{**status_.__dict__, "concurrent_jobs_active": max(0, status_.concurrent_jobs_active - 1)})
        _check(status_, kind=kind, job=job, check_concurrency=check_concurrency)

        fields = ["updated_at"]
        if _counts_as_video(kind, job):
            counter.videos_generated += 1
            fields.append("videos_generated")
            if job_key:
                counter.reserved_job_ids = [*(counter.reserved_job_ids or []), job_key]
                fields.append("reserved_job_ids")
        if kind == "regeneration":
            counter.regenerations_used += 1
            fields.append("regenerations_used")
        counter.save(update_fields=fields)

    logger.info(
        "quota_reserved",
        extra={"user_id": str(user.id), "job_id": job_key, "kind": kind, "used": counter.videos_generated, "quota": counter.videos_quota},
    )
    return counter


def release_quota(user, job) -> UsageCounter | None:
    """Refund the unit reserved for `job` (SPEC 7.2). No-op when nothing is held."""
    job_key = str(job.pk)
    with transaction.atomic():
        counter = (
            UsageCounter.objects.select_for_update()
            .filter(user=user, reserved_job_ids__contains=[job_key])
            .order_by("-period_start")
            .first()
        )
        if counter is None:
            logger.info("quota_release_noop", extra={"user_id": str(user.id), "job_id": job_key})
            return None
        counter.reserved_job_ids = [j for j in counter.reserved_job_ids if j != job_key]
        counter.videos_generated = max(0, counter.videos_generated - 1)
        counter.save(update_fields=["reserved_job_ids", "videos_generated", "updated_at"])
    logger.info(
        "quota_released",
        extra={"user_id": str(user.id), "job_id": job_key, "used": counter.videos_generated, "quota": counter.videos_quota},
    )
    return counter


def record_published(user) -> None:
    """Bump `videos_published` for reporting (called by the upload track on `published`)."""
    with transaction.atomic():
        counter, _ = _get_or_create_counter(user, for_update=True)
        counter.videos_published += 1
        counter.save(update_fields=["videos_published", "updated_at"])
