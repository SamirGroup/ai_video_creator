"""SPEC 5.27 `audit_logs` (append-only, FR-72, NFR-8). Retention: 24 months
(financial actions: 7 years) — a scheduled cleanup task is a Faza 2 follow-up.
"""
from __future__ import annotations

from django.db import models

from core.models import AppendOnlyModel


class ActorType(models.TextChoices):
    USER = "user", "User"
    STAFF = "staff", "Staff"
    SYSTEM = "system", "System"


class AuditLog(AppendOnlyModel):
    id = models.BigAutoField(primary_key=True)
    actor_type = models.CharField(max_length=10, choices=ActorType.choices)
    actor_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=128)
    resource_type = models.CharField(max_length=64)
    resource_id = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        indexes = [
            models.Index(fields=["resource_type", "resource_id"], name="ix_audit_logs_resource"),
            models.Index(fields=["actor_id", "created_at"], name="ix_audit_logs_actor"),
            models.Index(fields=["action", "created_at"], name="ix_audit_logs_action"),
        ]

    def __str__(self) -> str:
        return f"{self.actor_type}:{self.action}:{self.resource_type}:{self.resource_id}"
