"""Seed the MVP provider configuration (SPEC 5.24, Q3 decision).

Confirmed Q3 choices: LLM = Claude via **OpenRouter**, video-gen = Runway,
TTS = ElevenLabs, moderation = OpenAI Moderation. Only the two rows the script
stage actually needs are marked `is_primary` here — TTS/video-gen rows are
seeded inactive placeholders so the admin (FR-84) has something to edit when
those stages land, without them ever being picked up as "the primary provider"
by `get_primary_config()` in the meantime.

Idempotent: uses get_or_create keyed on (service, provider), so re-running or
re-applying the migration never creates a second primary row.

`secret_ref` holds only the NAME of an env var (C-5) — no key material is ever
written to the database, and therefore never to a DB dump or a backup.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import migrations

SEED_ROWS = [
    {
        "service": "llm",
        "provider": "openrouter",
        "display_name": "OpenRouter — Claude Sonnet 4.5",
        # SPEC section 9: model name lives in configuration, never in code.
        "model_name": "anthropic/claude-sonnet-4.5",
        "is_primary": True,
        "is_active": True,
        "priority": 10,
        "secret_ref": "OPENROUTER_API_KEY",
        # Anthropic list price via OpenRouter at time of writing: $3 / 1M input
        # tokens, $15 / 1M output tokens. `unit_cost_usd` is the flat fallback
        # (worst case = all-output); the split prices below are what actually
        # gets used, and OpenRouter's own `usage.cost` beats both when present.
        "unit_cost_usd": Decimal("0.015000"),
        "cost_unit": "per_1k_tokens",
        "rate_limit_per_min": 60,
        "config": {
            "base_url": "https://openrouter.ai/api/v1/chat/completions",
            "input_cost_per_1k_usd": "0.003",
            "output_cost_per_1k_usd": "0.015",
            "max_output_tokens": 4000,
            "temperature": 0.8,
            "request_timeout_sec": 120,
            # Ask OpenRouter to return the real billed cost in `usage`.
            "include_usage_cost": True,
            # Claude honours JSON-mode via OpenRouter's OpenAI-compatible shim;
            # the parser is defensive regardless (markdown fences, prose, etc.).
            "json_mode": True,
        },
    },
    {
        "service": "moderation",
        "provider": "openai_moderation",
        "display_name": "OpenAI Moderation (omni)",
        "model_name": "omni-moderation-latest",
        "is_primary": True,
        "is_active": True,
        "priority": 10,
        # Separate ref so the moderation gate can be rotated independently;
        # settings fall back to OPENAI_API_KEY when it is unset.
        "secret_ref": "OPENAI_MODERATION_API_KEY",
        "unit_cost_usd": Decimal("0.000000"),  # currently free of charge
        "cost_unit": "per_request",
        "rate_limit_per_min": 1000,
        "config": {
            "base_url": "https://api.openai.com/v1/moderations",
            "request_timeout_sec": 30,
            # FR-45: any category at/over `block_threshold` blocks the script.
            "block_threshold": 0.5,
            "flag_threshold": 0.2,
            # Stricter per-category floors for categories where even a weak
            # signal must not reach a published YouTube video (C-6, R-2).
            "category_thresholds": {
                "sexual/minors": 0.05,
                "self-harm/instructions": 0.1,
                "violence/graphic": 0.3,
                "harassment/threatening": 0.3,
                "hate/threatening": 0.2,
                "illicit/violent": 0.2,
            },
            "max_chars_per_chunk": 8000,
        },
    },
    # --- Placeholders for stages implemented later (inactive on purpose) ------
    {
        "service": "tts",
        "provider": "elevenlabs",
        "display_name": "ElevenLabs TTS",
        "model_name": "eleven_multilingual_v2",
        "is_primary": False,
        "is_active": False,
        "priority": 10,
        "secret_ref": "ELEVENLABS_API_KEY",
        "unit_cost_usd": Decimal("0.000180"),
        "cost_unit": "per_char",
        "rate_limit_per_min": None,
        "config": {"base_url": "https://api.elevenlabs.io/v1", "request_timeout_sec": 300},
    },
    {
        "service": "video_gen",
        "provider": "runway",
        "display_name": "Runway video generation",
        "model_name": "gen4_turbo",
        "is_primary": False,
        "is_active": False,
        "priority": 10,
        "secret_ref": "RUNWAY_API_KEY",
        "unit_cost_usd": Decimal("0.050000"),
        "cost_unit": "per_second",
        "rate_limit_per_min": None,
        "config": {"base_url": "https://api.dev.runwayml.com/v1", "request_timeout_sec": 600},
    },
]


def seed_providers(apps, schema_editor):
    ApiCredentialConfig = apps.get_model("providers", "ApiCredentialConfig")
    for row in SEED_ROWS:
        defaults = {k: v for k, v in row.items() if k not in ("service", "provider")}
        ApiCredentialConfig.objects.get_or_create(
            service=row["service"], provider=row["provider"], defaults=defaults
        )


def unseed_providers(apps, schema_editor):
    ApiCredentialConfig = apps.get_model("providers", "ApiCredentialConfig")
    for row in SEED_ROWS:
        ApiCredentialConfig.objects.filter(
            service=row["service"], provider=row["provider"]
        ).delete()


class Migration(migrations.Migration):

    dependencies = [("providers", "0001_initial")]

    operations = [migrations.RunPython(seed_providers, unseed_providers)]
