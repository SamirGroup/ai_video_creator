"""SPEC 5.3 `youtube_channels`, 5.4 `adsense_accounts`."""
from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.fields import EncryptedTextField
from core.models import TimestampedModel


class ConnectionStatus(models.TextChoices):
    CONNECTED = "connected", "Connected"
    DISCONNECTED = "disconnected", "Disconnected"
    REVOKED = "revoked", "Revoked"
    ERROR = "error", "Error"


class MonetizationSource(models.TextChoices):
    API = "api", "Detected via API"
    SELF_DECLARED = "self_declared", "Self-declared"
    UNKNOWN = "unknown", "Unknown"


class YouTubeChannel(TimestampedModel):
    """FR-10..FR-17. One creator account <-> one channel in MVP (FR-16 uniqueness)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="youtube_channels"
    )
    youtube_channel_id = models.CharField(max_length=64, unique=True)
    channel_title = models.CharField(max_length=255, blank=True, default="")
    channel_handle = models.CharField(max_length=100, blank=True, default="")
    thumbnail_url = models.TextField(blank=True, default="")
    subscriber_count = models.BigIntegerField(null=True, blank=True)
    video_count = models.BigIntegerField(null=True, blank=True)
    is_monetized = models.BooleanField(null=True, blank=True)  # NULL = unknown (FR-17)
    monetization_source = models.CharField(
        max_length=20, choices=MonetizationSource.choices, default=MonetizationSource.UNKNOWN
    )

    # AES-256-GCM/Fernet encrypted at the application layer — never returned by any API (C-5, NFR-2).
    access_token_enc = EncryptedTextField(null=True, blank=True)
    refresh_token_enc = EncryptedTextField(null=True, blank=True)
    token_key_version = models.SmallIntegerField(default=1)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    granted_scopes = ArrayField(models.CharField(max_length=128), default=list, blank=True)

    status = models.CharField(
        max_length=20, choices=ConnectionStatus.choices, default=ConnectionStatus.DISCONNECTED
    )
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    connected_at = models.DateTimeField(null=True, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "youtube_channels"
        indexes = [
            models.Index(fields=["user"], name="ix_yt_channels_user"),
            models.Index(fields=["status"], name="ix_yt_channels_status"),
        ]

    def __str__(self) -> str:
        return self.channel_title or self.youtube_channel_id


class AdSenseAccount(TimestampedModel):
    """FR-19, FR-20 — optional, independent OAuth consent (`adsense.readonly`)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="adsense_accounts"
    )
    adsense_account_id = models.CharField(max_length=64, unique=True)

    access_token_enc = EncryptedTextField(null=True, blank=True)
    refresh_token_enc = EncryptedTextField(null=True, blank=True)
    token_key_version = models.SmallIntegerField(default=1)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    granted_scopes = ArrayField(models.CharField(max_length=128), default=list, blank=True)

    status = models.CharField(
        max_length=20, choices=ConnectionStatus.choices, default=ConnectionStatus.DISCONNECTED
    )
    connected_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "adsense_accounts"
        indexes = [models.Index(fields=["user"], name="ix_adsense_accounts_user")]

    def __str__(self) -> str:
        return self.adsense_account_id


# --- Track C ---
class QuotaUsage(models.Model):
    """SPEC 5.26 `quota_usage` — per Google Cloud project, per Pacific-Time day
    (FR-58). The hot counter lives in Redis (`channels.quota`); this row is the
    durable write-through copy used for reporting and for re-seeding the cache
    after a Redis restart.
    """

    id = models.BigAutoField(primary_key=True)
    google_project_id = models.CharField(max_length=64)
    date_pt = models.DateField()
    units_used = models.IntegerField(default=0)
    uploads_used = models.IntegerField(default=0)
    units_limit = models.IntegerField()
    uploads_limit = models.IntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quota_usage"
        constraints = [
            models.UniqueConstraint(fields=["google_project_id", "date_pt"], name="uq_quota_usage_project_date")
        ]

    def __str__(self) -> str:
        return f"{self.google_project_id}:{self.date_pt}:{self.units_used}/{self.units_limit}"
