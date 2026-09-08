"""SPEC 5.22 `notifications`, 5.23 `notification_preferences` (FR-74..FR-77)."""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from video_pipeline.models import VideoJob


class NotificationChannel(models.TextChoices):
    EMAIL = "email", "Email"
    IN_APP = "in_app", "In-app"
    PUSH = "push", "Push"  # F2
    TELEGRAM = "telegram", "Telegram"  # F2


class NotificationStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    READ = "read", "Read"


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=64)
    channel = models.CharField(max_length=10, choices=NotificationChannel.choices)
    title = models.CharField(max_length=255)
    body = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    related_job = models.ForeignKey(
        VideoJob, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications"
    )
    status = models.CharField(max_length=10, choices=NotificationStatus.choices, default=NotificationStatus.QUEUED)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(fields=["user", "status", "-created_at"], name="ix_notifications_user_status"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.type}"


class NotificationPreference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences"
    )
    type = models.CharField(max_length=64)
    email_enabled = models.BooleanField(default=True)
    in_app_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "notification_preferences"
        constraints = [
            models.UniqueConstraint(fields=["user", "type"], name="uq_notification_pref_user_type")
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.type}"
