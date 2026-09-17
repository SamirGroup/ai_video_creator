"""SPEC 5.10 `content_preferences`."""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from channels.models import YouTubeChannel
from core.models import TimestampedModel


class AspectRatio(models.TextChoices):
    WIDE = "16:9", "16:9"
    VERTICAL = "9:16", "9:16"  # F2


class Frequency(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


class PrivacyStatus(models.TextChoices):
    PUBLIC = "public", "Public"
    UNLISTED = "unlisted", "Unlisted"
    PRIVATE = "private", "Private"


class ApprovalMode(models.TextChoices):
    REVIEW_REQUIRED = "review_required", "Review required"
    AUTO = "auto", "Auto-publish"


class ContentPreference(TimestampedModel):
    """FR-33..FR-37: niche, schedule, and approval-mode settings per channel."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="content_preferences",
    )
    channel = models.ForeignKey(
        YouTubeChannel, on_delete=models.CASCADE, related_name="content_preferences"
    )

    niche = models.CharField(max_length=64)
    custom_brief = models.TextField(blank=True, default="")
    brand_voice = models.TextField(blank=True, default="")
    banned_topics = ArrayField(
        models.CharField(max_length=128), default=list, blank=True
    )
    language = models.CharField(max_length=10)
    video_duration_sec = models.IntegerField()
    aspect_ratio = models.CharField(
        max_length=8, choices=AspectRatio.choices, default=AspectRatio.WIDE
    )

    frequency = models.CharField(max_length=10, choices=Frequency.choices)
    publish_time_local = models.TimeField()
    publish_timezone = models.CharField(max_length=64)
    publish_days = ArrayField(models.SmallIntegerField(), null=True, blank=True)

    youtube_privacy_status = models.CharField(
        max_length=10, choices=PrivacyStatus.choices, default=PrivacyStatus.PUBLIC
    )
    youtube_category_id = models.CharField(max_length=8, default="22")
    made_for_kids = models.BooleanField(default=False)

    approval_mode = models.CharField(
        max_length=20,
        choices=ApprovalMode.choices,
        default=ApprovalMode.REVIEW_REQUIRED,
    )
    auto_publish_on_timeout = models.BooleanField(default=False)

    voice_id = models.CharField(max_length=128, blank=True, default="")
    music_style = models.CharField(max_length=64, blank=True, default="")
    is_paused = models.BooleanField(default=False)
    automatic_schedule_enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "content_preferences"
        indexes = [models.Index(fields=["channel"], name="ix_content_prefs_channel")]

    def __str__(self) -> str:
        return f"{self.channel_id}:{self.niche}"


class ContentPlan(TimestampedModel):
    """Immutable proposal once approved; generation uses its preference snapshot."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="content_plans"
    )
    channel = models.ForeignKey(
        YouTubeChannel, on_delete=models.CASCADE, related_name="content_plans"
    )
    request_key = models.UUIDField()
    horizon = models.CharField(max_length=10, choices=Frequency.choices)
    item_count = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        default="pending",
        choices=[
            (x, x)
            for x in (
                "pending",
                "generating",
                "ready",
                "approved",
                "failed",
                "canceled",
            )
        ],
    )
    preference_snapshot = models.JSONField(default=dict)
    analysis = models.JSONField(default=dict)
    summary = models.TextField(blank=True, default="")
    error_code = models.CharField(max_length=64, blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=4, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_key"], name="unique_plan_request"
            )
        ]


class ContentPlanItem(TimestampedModel):
    plan = models.ForeignKey(
        ContentPlan, on_delete=models.CASCADE, related_name="items"
    )
    position = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=100)
    brief = models.TextField()
    rationale = models.TextField(blank=True, default="")
    scheduled_for = models.DateTimeField()
    selected = models.BooleanField(default=True)
    job = models.OneToOneField(
        "video_pipeline.VideoJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plan_item",
    )

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "position"], name="unique_plan_position"
            )
        ]
