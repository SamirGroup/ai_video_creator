"""SPEC 5.24 `api_credentials_config` and 5.25 `api_usage_logs` (FR-51, FR-84).

Design rules baked into these tables:

* **No secret ever lands in the database.** `ApiCredentialConfig.secret_ref` holds
  the *name* of a Django setting / environment variable (e.g. `OPENROUTER_API_KEY`),
  never the key material itself (C-5, NFR-3, FR-84). `resolve_secret()` is the only
  place that dereferences it.
* **No model name is hardcoded in application code.** Which LLM/TTS/video provider
  and which model is used is a row in this table, editable from the admin panel
  (FR-84, SPEC section 9: "Model nomi konfiguratsiyada, kodda hardcode emas").
* **Exactly one primary per service** — enforced by a partial unique index so a
  misconfigured admin action can't make provider selection ambiguous.
* Every outbound provider call writes one `ApiUsageLog` row with units + USD cost
  so `video_jobs.total_cost_usd` and the per-creator P&L report (FR-51, FR-82)
  have a single, auditable source of truth.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimestampedModel


class ServiceType(models.TextChoices):
    LLM = "llm", "LLM (script generation)"
    TTS = "tts", "Text-to-speech"
    VIDEO_GEN = "video_gen", "Video generation"
    MUSIC = "music", "Music generation"
    MODERATION = "moderation", "Content moderation"
    TRANSLATION = "translation", "Translation"
    STT = "stt", "Speech-to-text"


class CostUnit(models.TextChoices):
    PER_1K_TOKENS = "per_1k_tokens", "Per 1k tokens"
    PER_CHAR = "per_char", "Per character"
    PER_SECOND = "per_second", "Per second"
    PER_CLIP = "per_clip", "Per clip"
    PER_REQUEST = "per_request", "Per request"


class ApiCredentialConfig(TimestampedModel):
    """SPEC 5.24 — which provider/model serves each pipeline stage, and what it costs."""

    service = models.CharField(max_length=20, choices=ServiceType.choices)
    provider = models.CharField(
        max_length=64,
        help_text="openrouter | elevenlabs | azure_tts | runway | veo | svd | suno | "
        "openai_moderation | aws_rekognition | deepl | whisper",
    )
    display_name = models.CharField(max_length=128, blank=True, default="")
    model_name = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Provider-side model id, e.g. 'anthropic/claude-sonnet-4.5'. "
        "Never hardcoded in application code (SPEC section 9).",
    )

    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    priority = models.SmallIntegerField(
        default=100,
        help_text="Lower value = tried first when failing over (F2 routing).",
    )

    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Non-secret provider parameters: base_url, temperature, thresholds, "
        "timeouts, per-token prices. NEVER put API keys here.",
    )

    unit_cost_usd = models.DecimalField(
        max_digits=14, decimal_places=6, null=True, blank=True
    )
    cost_unit = models.CharField(
        max_length=32, choices=CostUnit.choices, blank=True, default=""
    )

    secret_ref = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Name of the env var / Django setting holding the API key "
        "(e.g. OPENROUTER_API_KEY) — NOT the key itself (C-5, FR-84).",
    )
    rate_limit_per_min = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "api_credentials_config"
        constraints = [
            models.UniqueConstraint(
                fields=["service"],
                condition=Q(is_primary=True, deleted_at__isnull=True),
                name="uq_api_credentials_one_primary_per_service",
            ),
        ]
        indexes = [
            models.Index(
                fields=["service", "is_active"], name="ix_api_creds_service_active"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.service}:{self.provider}:{self.model_name or '-'}"

    # -- secret handling -----------------------------------------------------
    def resolve_secret(self) -> str:
        """Dereference `secret_ref` from Django settings, then the process env.

        Returns "" when unset; callers decide whether that is fatal. The value is
        returned but never logged, never serialized and never stored (NFR-3).
        """
        if not self.secret_ref:
            return ""
        _missing = object()
        value = getattr(settings, self.secret_ref, _missing)
        if value is _missing:
            # Not a real Django setting at all (e.g. an ad-hoc name) — fall
            # back to a raw process env var. If the setting DOES exist but is
            # falsy/empty, that is an explicit "not configured" and must NOT
            # silently fall through to a stale os.environ value (settings.py
            # loads .env into os.environ at import time, so that fallback
            # would defeat any test/deploy that overrides the setting itself).
            value = os.environ.get(self.secret_ref, "")
        return value or ""

    def has_secret(self) -> bool:
        return bool(self.resolve_secret())

    # -- config helpers ------------------------------------------------------
    def get_option(self, key: str, default=None):
        cfg = self.config if isinstance(self.config, dict) else {}
        value = cfg.get(key, default)
        return default if value is None else value


class ApiUsageLog(models.Model):
    """SPEC 5.25 — one row per outbound provider call (FR-51 cost tracking).

    Written on success *and* failure: a 429/500 that burned latency and (for some
    providers) tokens is still operational truth needed for FR-52 cost ceilings
    and NFR-32 "daily AI spend over budget" alerting.
    """

    id = models.BigAutoField(primary_key=True)
    job = models.ForeignKey(
        "video_pipeline.VideoJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="api_usage_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="api_usage_logs",
    )

    service = models.CharField(max_length=20, choices=ServiceType.choices)
    provider = models.CharField(max_length=64)
    model = models.CharField(max_length=128, blank=True, default="")
    operation = models.CharField(
        max_length=64, help_text="e.g. script_generation, script_moderation"
    )

    units = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    unit_type = models.CharField(max_length=32, blank=True, default="")
    cost_usd = models.DecimalField(max_digits=14, decimal_places=6, default=0)

    pricing_snapshot = models.JSONField(default=dict)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.IntegerField(null=True, blank=True)
    http_status = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    request_id = models.CharField(max_length=128, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "api_usage_logs"
        indexes = [
            models.Index(fields=["job"], name="ix_api_usage_job"),
            models.Index(
                fields=["provider", "created_at"], name="ix_api_usage_provider_time"
            ),
            models.Index(fields=["user", "created_at"], name="ix_api_usage_user_time"),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.operation}:{self.cost_usd}"
