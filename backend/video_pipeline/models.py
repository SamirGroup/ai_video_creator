"""SPEC 5.11 `video_jobs`, 5.12 `video_job_steps`, 5.13 `video_assets`,
5.14 `music_tracks`.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from channels.models import YouTubeChannel
from content_planning.models import ContentPreference
from core.models import AppendOnlyModel, TimestampedModel


class JobTrigger(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    MANUAL = "manual", "Manual"
    REGENERATION = "regeneration", "Regeneration"


class JobStatus(models.TextChoices):
    """SPEC 7.2 status model."""

    DRAFT = "draft", "Draft"
    SCHEDULED = "scheduled", "Scheduled"
    QUEUED = "queued", "Queued"
    GENERATING_SCRIPT = "generating_script", "Generating script"
    SCRIPT_READY = "script_ready", "Script ready"
    MODERATING_SCRIPT = "moderating_script", "Moderating script"
    GENERATING_VOICE = "generating_voice", "Generating voice"
    VOICE_READY = "voice_ready", "Voice ready"
    GENERATING_VISUALS = "generating_visuals", "Generating visuals"
    VISUALS_READY = "visuals_ready", "Visuals ready"
    ASSEMBLING = "assembling", "Assembling"
    ASSEMBLED = "assembled", "Assembled"
    MODERATING_FINAL = "moderating_final", "Moderating final"
    MODERATION_REVIEW = "moderation_review", "Moderation review"
    MODERATION_REJECTED = "moderation_rejected", "Moderation rejected"
    AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
    CHANGES_REQUESTED = "changes_requested", "Changes requested"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    UPLOAD_QUEUED = "upload_queued", "Upload queued"
    UPLOADING = "uploading", "Uploading"
    UPLOADED = "uploaded", "Uploaded"
    PUBLISHED = "published", "Published"
    YOUTUBE_REJECTED = "youtube_rejected", "YouTube rejected"
    RETRYING = "retrying", "Retrying"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"
    DELETED_ON_YOUTUBE = "deleted_on_youtube", "Deleted on YouTube"

    @classmethod
    def terminal_statuses(cls) -> set[str]:
        return {
            cls.PUBLISHED,
            cls.REJECTED,
            cls.MODERATION_REJECTED,
            cls.YOUTUBE_REJECTED,
            cls.EXPIRED,
            cls.FAILED,
            cls.CANCELED,
        }


class Stage(models.TextChoices):
    SCRIPT = "script", "Script"
    VOICE = "voice", "Voice"
    VISUALS = "visuals", "Visuals"
    ASSEMBLY = "assembly", "Assembly"
    MODERATION = "moderation", "Moderation"
    UPLOAD = "upload", "Upload"


class VideoJob(TimestampedModel):
    """Central pipeline table (SPEC 5.11)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="video_jobs"
    )
    channel = models.ForeignKey(
        YouTubeChannel, on_delete=models.CASCADE, related_name="video_jobs"
    )
    preference = models.ForeignKey(
        ContentPreference,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="video_jobs",
    )
    trigger = models.CharField(max_length=20, choices=JobTrigger.choices)
    parent_job = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regenerations",
    )

    status = models.CharField(
        max_length=32, choices=JobStatus.choices, default=JobStatus.DRAFT
    )
    current_stage = models.CharField(
        max_length=20, choices=Stage.choices, null=True, blank=True
    )

    generation_context = models.JSONField(default=dict, blank=True)
    scheduled_for = models.DateTimeField()

    title = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, default="")
    tags = ArrayField(models.CharField(max_length=64), default=list, blank=True)
    script_text = models.TextField(blank=True, default="")
    script_meta = models.JSONField(default=dict, blank=True)
    language = models.CharField(max_length=10, blank=True, default="")
    duration_sec = models.IntegerField(null=True, blank=True)

    moderation_metadata_sha256 = models.CharField(max_length=64, blank=True, default="")
    moderation_approved_sha256 = models.CharField(max_length=64, blank=True, default="")
    final_video_s3_key = models.TextField(blank=True, default="")
    thumbnail_s3_key = models.TextField(blank=True, default="")
    preview_token = models.CharField(max_length=64, blank=True, default="")
    preview_expires_at = models.DateTimeField(null=True, blank=True)

    approval_requested_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    approval_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_jobs",
    )
    rejection_reason = models.TextField(blank=True, default="")
    regeneration_count = models.SmallIntegerField(default=0)

    youtube_video_id = models.CharField(max_length=32, blank=True, default="")
    youtube_url = models.TextField(blank=True, default="")
    published_at = models.DateTimeField(null=True, blank=True)
    youtube_upload_status = models.CharField(max_length=32, blank=True, default="")
    youtube_rejection_reason = models.CharField(max_length=64, blank=True, default="")

    is_platform_generated = models.BooleanField(default=True)  # FR-65
    deleted_on_youtube = models.BooleanField(default=False)  # FR-60

    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    retry_count = models.SmallIntegerField(default=0)
    total_cost_usd = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "video_jobs"
        indexes = [
            models.Index(fields=["user", "status"], name="ix_video_jobs_user_status"),
            models.Index(
                fields=["channel", "published_at"], name="ix_video_jobs_channel_pub"
            ),
            models.Index(fields=["status"], name="ix_video_jobs_status"),
            models.Index(fields=["scheduled_for"], name="ix_video_jobs_scheduled_for"),
            models.Index(fields=["youtube_video_id"], name="ix_video_jobs_yt_id"),
        ]

    def __str__(self) -> str:
        return f"{self.id}:{self.status}"

    def is_terminal(self) -> bool:
        return self.status in JobStatus.terminal_statuses()


class StepStatus(models.TextChoices):
    STARTED = "started", "Started"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


class VideoJobStep(AppendOnlyModel):
    """SPEC 5.12: append-only per-attempt history, one row per (job, stage, attempt)."""

    id = models.BigAutoField(primary_key=True)
    job = models.ForeignKey(VideoJob, on_delete=models.CASCADE, related_name="steps")
    stage = models.CharField(max_length=20, choices=Stage.choices)
    attempt = models.SmallIntegerField()
    status = models.CharField(max_length=20, choices=StepStatus.choices)
    provider = models.CharField(max_length=64, blank=True, default="")
    provider_request_id = models.CharField(max_length=128, blank=True, default="")
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    cost_usd = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_detail = models.TextField(blank=True, default="")
    output_ref = models.TextField(blank=True, default="")

    class Meta:
        db_table = "video_job_steps"
        indexes = [
            models.Index(
                fields=["job", "stage", "attempt"], name="ix_video_job_steps_lookup"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.job_id}:{self.stage}:{self.attempt}"


class AssetKind(models.TextChoices):
    SCRIPT = "script", "Script"
    AUDIO_VOICE = "audio_voice", "Audio (voice)"
    AUDIO_MUSIC = "audio_music", "Audio (music)"
    VISUAL_CLIP = "visual_clip", "Visual clip"
    SUBTITLE = "subtitle", "Subtitle"
    THUMBNAIL = "thumbnail", "Thumbnail"
    FINAL_VIDEO = "final_video", "Final video"


class VideoAsset(TimestampedModel):
    """SPEC 5.13: per-stage checkpoint artifact so retries never redo finished stages."""

    job = models.ForeignKey(VideoJob, on_delete=models.CASCADE, related_name="assets")
    kind = models.CharField(max_length=20, choices=AssetKind.choices)
    s3_key = models.TextField()
    mime_type = models.CharField(max_length=64, blank=True, default="")
    size_bytes = models.BigIntegerField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True, default="")
    provider = models.CharField(max_length=64, blank=True, default="")
    license_ref = models.CharField(max_length=128, blank=True, default="")
    sequence_index = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "video_assets"
        indexes = [
            models.Index(fields=["job", "kind"], name="ix_video_assets_job_kind")
        ]

    def __str__(self) -> str:
        return f"{self.job_id}:{self.kind}"


class MusicTrack(models.Model):
    """SPEC 5.14: licensed background-music library (FR-47 — no third-party content)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    s3_key = models.TextField()
    duration_ms = models.IntegerField()
    mood = models.CharField(max_length=64, blank=True, default="")
    bpm = models.IntegerField(null=True, blank=True)
    license_type = models.CharField(max_length=64)
    license_document_url = models.TextField(blank=True, default="")
    attribution_required = models.BooleanField(default=False)
    attribution_text = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "music_tracks"

    def __str__(self) -> str:
        return self.title


class VideoRevision(TimestampedModel):
    """A rejected revision remains intact; every correction gets a new job and fresh moderation."""

    previous_job = models.OneToOneField(
        VideoJob, on_delete=models.CASCADE, related_name="next_revision"
    )
    replacement_job = models.OneToOneField(
        VideoJob, on_delete=models.CASCADE, related_name="revision_origin"
    )
    root_job = models.ForeignKey(
        VideoJob, on_delete=models.CASCADE, related_name="revision_history"
    )
    number = models.PositiveSmallIntegerField()
    reason = models.TextField()
    findings = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["root_job", "number"], name="unique_video_revision_number"
            )
        ]
