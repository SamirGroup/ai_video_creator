"""SPEC 5.8 `contract_versions`, 5.9 `contracts`."""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from core.models import TimestampedModel


class ContractVersion(models.Model):
    """FR-28: versioned contract template. Immutable once published; new terms
    are a new version row, never an in-place edit.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=255)
    body_markdown = models.TextField()
    body_sha256 = models.CharField(max_length=64, editable=False)
    locale = models.CharField(max_length=5, default="en")
    revenue_share_platform_pct = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    revenue_share_creator_pct = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    effective_from = models.DateTimeField()
    is_active = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contract_versions"
        ordering = ["-effective_from"]

    def __str__(self) -> str:
        return self.version

    def save(self, *args, **kwargs):
        import hashlib

        self.body_sha256 = hashlib.sha256(self.body_markdown.encode("utf-8")).hexdigest()
        super().save(*args, **kwargs)


class ContractStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUPERSEDED = "superseded", "Superseded"
    TERMINATED = "terminated", "Terminated"


class Contract(models.Model):
    """FR-29..FR-32: signed consent record. Append-only in practice — the only
    permitted mutation after creation is a status transition (superseded/terminated),
    enforced in the service layer rather than the DB layer here for now.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contracts")
    contract_version = models.ForeignKey(
        ContractVersion, on_delete=models.PROTECT, related_name="contracts"
    )
    signed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, default="")
    body_sha256 = models.CharField(max_length=64)
    pdf_s3_key = models.TextField(blank=True, default="")

    consent_revenue_share = models.BooleanField(default=False)
    consent_publish_to_channel = models.BooleanField(default=False)
    consent_data_processing = models.BooleanField(default=False)
    consent_marketing = models.BooleanField(default=False)  # FR-30(d): optional, default OFF.

    status = models.CharField(max_length=20, choices=ContractStatus.choices, default=ContractStatus.ACTIVE)
    terminated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "contracts"
        indexes = [
            models.Index(fields=["user"], name="ix_contracts_user"),
            models.Index(fields=["status"], name="ix_contracts_status"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.contract_version_id}"
