"""Shared abstract base models (SPEC section 5, "Umumiy konvensiyalar").

Every business table extends `TimestampedModel` (UUID pk, created_at,
updated_at, deleted_at). Append-only tables (ledger, audit trail) extend
`AppendOnlyModel` instead, which blocks UPDATE/DELETE at the application
level (FR-72, 5.21).
"""
from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models


class TimestampedModel(models.Model):
    """Abstract base for business tables: UUID pk + created/updated/soft-delete."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        """Mark the row as deleted without removing it (business data retention)."""
        from django.utils import timezone

        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])


class AppendOnlyModel(models.Model):
    """Abstract base for append-only tables (audit_logs, ledger_entries, contracts
    status trail). Once a row is written it can never be UPDATEd or DELETEd —
    corrections are new rows (FR-72, NFR-16).
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "This record is append-only and cannot be modified after creation."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("This record is append-only and cannot be deleted.")
