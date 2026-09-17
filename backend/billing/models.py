"""SPEC 5.5 `plans`, 5.6 `subscriptions`, 5.30 `webhook_events`."""

from __future__ import annotations


from django.conf import settings
from django.db import models

from core.models import TimestampedModel


class BillingInterval(models.TextChoices):
    MONTH = "month", "Monthly"
    SIX_MONTHS = "six_months", "Every 6 months"


class Plan(TimestampedModel):
    """FR-21: kvota va feature flag'lar DB'da, kodda hardcode emas."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=100)
    price_amount = models.DecimalField(max_digits=14, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    billing_interval = models.CharField(max_length=20, choices=BillingInterval.choices)
    stripe_price_id = models.CharField(max_length=255, blank=True, default="")

    tax_pct = models.DecimalField(max_digits=5, decimal_places=2, default=12)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_label = models.CharField(max_length=150, blank=True, default="")
    discount_starts_at = models.DateTimeField(null=True, blank=True)
    discount_ends_at = models.DateTimeField(null=True, blank=True)
    ai_budget_enabled = models.BooleanField(default=False)
    stars_amount = models.PositiveIntegerField(default=0)
    videos_per_period = models.IntegerField()
    max_video_duration_sec = models.IntegerField()
    max_languages = models.IntegerField(default=1)
    concurrent_jobs = models.IntegerField(default=1)
    voice_cloning_enabled = models.BooleanField(default=False)
    priority_queue = models.BooleanField(default=False)
    sla_hours = models.IntegerField(null=True, blank=True)
    features = models.JSONField(default=dict, blank=True)

    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "plans"
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return self.code


class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing", "Trialing"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    SUSPENDED = "suspended", "Suspended"
    CANCELED = "canceled", "Canceled"
    EXPIRED = "expired", "Expired"


class Subscription(TimestampedModel):
    """FR-22..FR-27, FR-70a, FR-70b."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    stripe_subscription_id = models.CharField(
        max_length=255, unique=True, null=True, blank=True
    )
    # FR-70a: required before the contract (and generation) can go `active`.
    default_payment_method_id = models.CharField(max_length=255, blank=True, default="")

    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIALING,
    )
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    grace_period_ends_at = models.DateTimeField(null=True, blank=True)
    revenue_share_paused = models.BooleanField(default=False)

    class Meta:
        db_table = "subscriptions"
        indexes = [
            models.Index(fields=["user"], name="ix_subscriptions_user"),
            models.Index(fields=["status"], name="ix_subscriptions_status"),
            models.Index(
                fields=["current_period_end"], name="ix_subscriptions_period_end"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.plan.code}"


class WebhookProvider(models.TextChoices):
    STRIPE = "stripe", "Stripe"
    GOOGLE = "google", "Google"


class WebhookEventStatus(models.TextChoices):
    RECEIVED = "received", "Received"
    PROCESSED = "processed", "Processed"
    FAILED = "failed", "Failed"
    IGNORED = "ignored", "Ignored"


class WebhookEvent(models.Model):
    """FR-25, NFR-5: idempotent webhook processing, signature verification logged."""

    id = models.BigAutoField(primary_key=True)
    provider = models.CharField(max_length=32, choices=WebhookProvider.choices)
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=64)
    payload = models.JSONField()
    signature_verified = models.BooleanField()
    status = models.CharField(
        max_length=20,
        choices=WebhookEventStatus.choices,
        default=WebhookEventStatus.RECEIVED,
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "webhook_events"
        indexes = [
            models.Index(
                fields=["provider", "event_type"], name="ix_webhook_events_type"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_id}"


# --- Track A ---------------------------------------------------------------
# SPEC 5.7 `usage_counters` (FR-23, FR-24). One row per (user, billing period).
# Counters are keyed by `subscription.current_period_start` so they reset on the
# subscription boundary, not the calendar month (FR-24). Users without a
# subscription (Free plan, A-20) fall back to a calendar-month window and a
# NULL subscription FK.
# ---------------------------------------------------------------------------
class UsageCounter(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="usage_counters",
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_counters",
    )
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    videos_quota = models.IntegerField(default=0)
    videos_generated = models.IntegerField(default=0)
    videos_published = models.IntegerField(default=0)
    regenerations_used = models.IntegerField(default=0)
    total_cost_usd = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    # Job ids currently holding a reservation. Lets reserve/release be idempotent
    # under Celery's at-least-once delivery (a double `release_quota` is a no-op).
    reserved_job_ids = models.JSONField(default=list, blank=True)
    # Set once per period when the "quota exhausted" notification was sent, so
    # the 15-minute scheduler does not nag the creator every run.
    exhausted_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "usage_counters"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "period_start"], name="uq_usage_counter_user_period"
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "period_end"], name="ix_usage_counters_user_end"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.period_start:%Y-%m-%d}:{self.videos_generated}/{self.videos_quota}"

    @property
    def videos_remaining(self) -> int:
        return max(0, self.videos_quota - self.videos_generated)


class AIWallet(TimestampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_wallet"
    )
    balance_usd = models.DecimalField(max_digits=16, decimal_places=6, default=0)
    reserved_usd = models.DecimalField(max_digits=16, decimal_places=6, default=0)


class AIWalletEntry(models.Model):
    wallet = models.ForeignKey(
        AIWallet, on_delete=models.PROTECT, related_name="entries"
    )
    reference = models.CharField(max_length=200, unique=True)
    amount_usd = models.DecimalField(max_digits=16, decimal_places=6)
    kind = models.CharField(max_length=32)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class AIBudgetReservation(models.Model):
    job = models.OneToOneField(
        "video_pipeline.VideoJob",
        on_delete=models.PROTECT,
        related_name="budget_reservation",
    )
    wallet = models.ForeignKey(AIWallet, on_delete=models.PROTECT)
    remaining_usd = models.DecimalField(max_digits=16, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)


class AIWalletHold(models.Model):
    wallet = models.ForeignKey(AIWallet, on_delete=models.PROTECT)
    reference = models.CharField(max_length=200, unique=True)
    amount_usd = models.DecimalField(max_digits=16, decimal_places=6)
    released = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
