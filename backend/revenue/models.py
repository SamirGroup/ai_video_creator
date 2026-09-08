"""SPEC 5.16 `revenue_records`, 5.17 `revenue_share_statements`, 5.18 `invoices`,
5.21 `ledger_entries` (append-only financial source of truth, FR-72).
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from contracts.models import Contract
from core.models import AppendOnlyModel, TimestampedModel
from video_pipeline.models import VideoJob


class RevenueSource(models.TextChoices):
    YOUTUBE_ANALYTICS = "youtube_analytics", "YouTube Analytics"
    ADSENSE = "adsense", "AdSense"


class RevenueRecord(models.Model):
    """FR-61..FR-66. UNIQUE(source, channel_id, youtube_video_id, date) for
    idempotent daily upsert (FR-62) — enforced below.
    """

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="revenue_records")
    channel = models.ForeignKey(
        "channels.YouTubeChannel", on_delete=models.CASCADE, related_name="revenue_records"
    )
    job = models.ForeignKey(
        VideoJob, on_delete=models.SET_NULL, null=True, blank=True, related_name="revenue_records"
    )
    youtube_video_id = models.CharField(max_length=32, blank=True, default="")
    source = models.CharField(max_length=20, choices=RevenueSource.choices)
    date = models.DateField()

    views = models.BigIntegerField(default=0)
    estimated_minutes_watched = models.BigIntegerField(default=0)
    estimated_revenue = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    estimated_ad_revenue = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    cpm = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    rpm = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")

    is_final = models.BooleanField(default=False)  # FR-63
    synced_at = models.DateTimeField()
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "revenue_records"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "channel", "youtube_video_id", "date"],
                name="uq_revenue_record_upsert_key",
            )
        ]
        indexes = [
            models.Index(fields=["user", "date"], name="ix_revenue_records_user_date"),
            models.Index(fields=["is_final", "date"], name="ix_revenue_records_final_date"),
        ]

    def __str__(self) -> str:
        return f"{self.channel_id}:{self.date}:{self.source}"


class StatementStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    FINALIZED = "finalized", "Finalized"
    INVOICED = "invoiced", "Invoiced"
    PAID = "paid", "Paid"
    DISPUTED = "disputed", "Disputed"
    WRITTEN_OFF = "written_off", "Written off"
    CARRIED_FORWARD = "carried_forward", "Carried forward"


class RevenueShareStatement(TimestampedModel):
    """FR-67..FR-69."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="revenue_share_statements"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    currency = models.CharField(max_length=3, default="USD")
    gross_revenue = models.DecimalField(max_digits=14, decimal_places=4)
    platform_share_pct = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    platform_share_amount = models.DecimalField(max_digits=14, decimal_places=4)
    creator_share_amount = models.DecimalField(max_digits=14, decimal_places=4)
    video_count = models.IntegerField(default=0)
    breakdown = models.JSONField(default=dict, blank=True)
    contract = models.ForeignKey(
        Contract, on_delete=models.PROTECT, related_name="revenue_share_statements"
    )
    status = models.CharField(max_length=20, choices=StatementStatus.choices, default=StatementStatus.DRAFT)
    finalized_at = models.DateTimeField(null=True, blank=True)
    disputed_at = models.DateTimeField(null=True, blank=True)
    dispute_reason = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    carried_forward_from = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "revenue_share_statements"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "period_start", "period_end"], name="uq_statement_period"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.period_start}-{self.period_end}"


class InvoiceKind(models.TextChoices):
    SUBSCRIPTION = "subscription", "Subscription"
    REVENUE_SHARE = "revenue_share", "Revenue share"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    OPEN = "open", "Open"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    VOID = "void", "Void"
    UNCOLLECTIBLE = "uncollectible", "Uncollectible"


class Invoice(TimestampedModel):
    """FR-70, FR-70a, FR-70b."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="invoices")
    statement = models.ForeignKey(
        RevenueShareStatement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    subscription = models.ForeignKey(
        "billing.Subscription", on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    kind = models.CharField(max_length=20, choices=InvoiceKind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    stripe_invoice_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)
    due_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    attempts = models.SmallIntegerField(default=0)
    pdf_url = models.TextField(blank=True, default="")

    class Meta:
        db_table = "invoices"
        indexes = [models.Index(fields=["user", "status"], name="ix_invoices_user_status")]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.kind}:{self.amount}"


class LedgerRefType(models.TextChoices):
    INVOICE = "invoice", "Invoice"
    STATEMENT = "statement", "Statement"
    PAYOUT = "payout", "Payout"
    SUBSCRIPTION = "subscription", "Subscription"
    ADJUSTMENT = "adjustment", "Adjustment"
    REFUND = "refund", "Refund"


class LedgerDirection(models.TextChoices):
    DEBIT = "debit", "Debit"
    CREDIT = "credit", "Credit"


class LedgerEntry(AppendOnlyModel):
    """SPEC 5.21: append-only financial source of truth. UPDATE/DELETE are
    blocked at the application layer by `AppendOnlyModel` (FR-72).
    """

    id = models.BigAutoField(primary_key=True)
    entry_uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_entries"
    )
    ref_type = models.CharField(max_length=20, choices=LedgerRefType.choices)
    ref_id = models.UUIDField()
    direction = models.CharField(max_length=10, choices=LedgerDirection.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    description = models.TextField(blank=True, default="")
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    reversal_of = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ledger_entries"
        indexes = [
            models.Index(fields=["ref_type", "ref_id"], name="ix_ledger_entries_ref"),
            models.Index(fields=["user", "occurred_at"], name="ix_ledger_entries_user_time"),
        ]

    def __str__(self) -> str:
        return f"{self.direction}:{self.amount}:{self.ref_type}:{self.ref_id}"


# ---------------------------------------------------------------------------
# --- Track D --- Dormant Stripe Connect schema (FR-71, A-12, SPEC 5.19/5.20).
# Tables exist so the F2 reverse-money-flow can be enabled without a schema
# migration; nothing in MVP writes to them and no endpoint exposes them.
# ---------------------------------------------------------------------------


class ConnectedAccountType(models.TextChoices):
    EXPRESS = "express", "Express"
    STANDARD = "standard", "Standard"


class ConnectOnboardingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETE = "complete", "Complete"
    RESTRICTED = "restricted", "Restricted"


class StripeConnectedAccount(TimestampedModel):
    """SPEC 5.19 `stripe_connected_accounts` — schema only in MVP (FR-71)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stripe_connected_account"
    )
    stripe_account_id = models.CharField(max_length=255, unique=True)
    account_type = models.CharField(
        max_length=20, choices=ConnectedAccountType.choices, default=ConnectedAccountType.EXPRESS
    )
    country = models.CharField(max_length=2, blank=True, default="")
    default_currency = models.CharField(max_length=3, default="USD")
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)
    details_submitted = models.BooleanField(default=False)
    requirements = models.JSONField(default=dict, blank=True)
    onboarding_status = models.CharField(
        max_length=20, choices=ConnectOnboardingStatus.choices, default=ConnectOnboardingStatus.PENDING
    )

    class Meta:
        db_table = "stripe_connected_accounts"

    def __str__(self) -> str:
        return self.stripe_account_id


class PayoutStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REVERSED = "reversed", "Reversed"


class Payout(TimestampedModel):
    """SPEC 5.20 `payouts` — schema only in MVP (FR-71)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payouts")
    connected_account = models.ForeignKey(
        StripeConnectedAccount, on_delete=models.PROTECT, related_name="payouts"
    )
    statement = models.ForeignKey(
        RevenueShareStatement, on_delete=models.SET_NULL, null=True, blank=True, related_name="payouts"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    stripe_transfer_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    status = models.CharField(max_length=20, choices=PayoutStatus.choices, default=PayoutStatus.PENDING)
    failure_reason = models.TextField(blank=True, default="")
    initiated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payouts"
        indexes = [models.Index(fields=["user", "status"], name="ix_payouts_user_status")]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.amount}:{self.status}"
