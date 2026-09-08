"""SPEC 5.15 `moderation_logs` (FR-45..FR-49)."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from video_pipeline.models import VideoJob


class ModerationStage(models.TextChoices):
    SCRIPT = "script", "Script"
    AUDIO = "audio", "Audio"
    VISUAL = "visual", "Visual"
    FINAL = "final", "Final"


class ModerationVerdict(models.TextChoices):
    PASS = "pass", "Pass"
    FLAG = "flag", "Flag"
    BLOCK = "block", "Block"


class ReviewDecision(models.TextChoices):
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ModerationLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    job = models.ForeignKey(VideoJob, on_delete=models.CASCADE, related_name="moderation_logs")
    stage = models.CharField(max_length=20, choices=ModerationStage.choices)
    provider = models.CharField(max_length=64)
    verdict = models.CharField(max_length=10, choices=ModerationVerdict.choices)
    categories = models.JSONField(default=dict, blank=True)
    threshold_config = models.JSONField(default=dict, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    review_decision = models.CharField(
        max_length=10, choices=ReviewDecision.choices, null=True, blank=True
    )
    review_reason = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "moderation_logs"
        indexes = [
            models.Index(fields=["job"], name="ix_moderation_logs_job"),
            models.Index(fields=["verdict", "reviewed_at"], name="ix_moderation_logs_verdict"),
        ]

    def __str__(self) -> str:
        return f"{self.job_id}:{self.stage}:{self.verdict}"
