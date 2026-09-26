"""Payoneer merchant accounts managed from the admin panel.

Several accounts can coexist (for example a sandbox and a live one, or two
legal entities). Secrets are encrypted at rest and never serialized back out;
the admin API only reports whether each one is set.
"""

import secrets

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.fields import EncryptedTextField
from core.models import TimestampedModel


class Environment(models.TextChoices):
    SANDBOX = "sandbox", "Sandbox"
    LIVE = "live", "Live"


def new_notification_token():
    return secrets.token_urlsafe(32)


class PayoneerAccount(TimestampedModel):
    label = models.CharField(max_length=120)
    environment = models.CharField(
        max_length=10, choices=Environment.choices, default=Environment.SANDBOX
    )
    is_active = models.BooleanField(default=True)

    # Payoneer Checkout: accepting card payments on a hosted page.
    checkout_enabled = models.BooleanField(default=False)
    is_default_checkout = models.BooleanField(default=False)
    merchant_code = models.CharField(max_length=120, blank=True)
    payment_token_enc = EncryptedTextField(null=True, blank=True)
    division = models.CharField(max_length=120, blank=True)
    # Sent back by Payoneer as a header on every status notification, which
    # carry no signature of their own.
    notification_token_enc = EncryptedTextField(default=new_notification_token)

    # Payoneer Mass Payouts: paying partners and contractors.
    payouts_enabled = models.BooleanField(default=False)
    is_default_payouts = models.BooleanField(default=False)
    program_id = models.CharField(max_length=64, blank=True)
    client_id = models.CharField(max_length=255, blank=True)
    client_secret_enc = EncryptedTextField(null=True, blank=True)

    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_check_ok = models.BooleanField(null=True, blank=True)
    last_check_detail = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-is_active", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default_checkout"],
                condition=models.Q(is_default_checkout=True),
                name="one_default_payoneer_checkout",
            ),
            models.UniqueConstraint(
                fields=["is_default_payouts"],
                condition=models.Q(is_default_payouts=True),
                name="one_default_payoneer_payouts",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.environment})"

    @property
    def checkout_ready(self):
        return bool(
            self.is_active
            and self.checkout_enabled
            and self.merchant_code
            and self.payment_token_enc
            and self.division
        )

    @property
    def payouts_ready(self):
        return bool(
            self.is_active
            and self.payouts_enabled
            and self.program_id
            and self.client_id
            and self.client_secret_enc
        )


class PayeeStatus(models.TextChoices):
    INVITED = "invited", "Invited"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class PayoneerPayee(TimestampedModel):
    """A person who receives payouts. `payee_id` is our identifier at Payoneer."""

    account = models.ForeignKey(
        PayoneerAccount, on_delete=models.PROTECT, related_name="payees"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payoneer_payees",
    )
    display_name = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    payee_id = models.CharField(max_length=64)
    status = models.CharField(
        max_length=12, choices=PayeeStatus.choices, default=PayeeStatus.INVITED
    )
    provider_status = models.CharField(max_length=60, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "payee_id"], name="unique_payoneer_payee"
            )
        ]


class PayoutStatus(models.TextChoices):
    SUBMITTING = "submitting", "Submitting"
    PENDING = "pending", "Pending"
    TRANSFERRED = "transferred", "Transferred"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


class PayoneerPayout(TimestampedModel):
    account = models.ForeignKey(
        PayoneerAccount, on_delete=models.PROTECT, related_name="payouts"
    )
    payee = models.ForeignKey(
        PayoneerPayee, on_delete=models.PROTECT, related_name="payouts"
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(1)]
    )
    currency = models.CharField(max_length=3, default="USD")
    description = models.CharField(max_length=200)
    # Payoneer deduplicates on this reference, so a retried submission can
    # never pay twice.
    client_reference_id = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=12, choices=PayoutStatus.choices, default=PayoutStatus.SUBMITTING
    )
    provider_status = models.CharField(max_length=60, blank=True)
    payout_id = models.CharField(max_length=120, blank=True)
    reason = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
