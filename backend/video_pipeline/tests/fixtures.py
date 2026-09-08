"""Shared test doubles for the script stage.

`unittest.mock` only — no `responses`/`vcr` dependency, and (per the constraint
in this task and NFR-38) **no test in this package ever opens a socket**. The
fake session below is the single seam where HTTP would have happened.
"""
from __future__ import annotations

import json
from decimal import Decimal

from providers.models import ApiCredentialConfig, CostUnit, ServiceType


class FakeResponse:
    """Minimal stand-in for `requests.Response`."""

    def __init__(self, status_code=200, payload=None, headers=None, text_body=None):
        self.status_code = status_code
        self._payload = payload
        self._text_body = text_body
        self.headers = headers or {}

    def json(self):
        if self._text_body is not None:
            return json.loads(self._text_body)  # raises ValueError like requests does
        return self._payload


class FakeSession:
    """Records the outgoing request and replays a queued response (or exception)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        item = self.responses.pop(0) if self.responses else FakeResponse(500)
        if isinstance(item, Exception):
            raise item
        return item


def llm_config(**overrides) -> ApiCredentialConfig:
    """Unsaved `api_credentials_config` row — usable without a database."""
    defaults = {
        "service": ServiceType.LLM,
        "provider": "openrouter",
        "display_name": "OpenRouter — Claude Sonnet 4.5",
        "model_name": "anthropic/claude-sonnet-4.5",
        "is_primary": True,
        "is_active": True,
        "secret_ref": "OPENROUTER_API_KEY",
        "unit_cost_usd": Decimal("0.015000"),
        "cost_unit": CostUnit.PER_1K_TOKENS,
        "config": {
            "input_cost_per_1k_usd": "0.003",
            "output_cost_per_1k_usd": "0.015",
            "max_output_tokens": 1000,
            "temperature": 0.7,
            "request_timeout_sec": 30,
            "json_mode": True,
            "include_usage_cost": True,
        },
    }
    defaults.update(overrides)
    return ApiCredentialConfig(**defaults)


def moderation_config(**overrides) -> ApiCredentialConfig:
    defaults = {
        "service": ServiceType.MODERATION,
        "provider": "openai_moderation",
        "display_name": "OpenAI Moderation (omni)",
        "model_name": "omni-moderation-latest",
        "is_primary": True,
        "is_active": True,
        "secret_ref": "OPENAI_MODERATION_API_KEY",
        "unit_cost_usd": Decimal("0"),
        "cost_unit": CostUnit.PER_REQUEST,
        "config": {
            "block_threshold": 0.5,
            "flag_threshold": 0.2,
            "category_thresholds": {"sexual/minors": 0.05},
            "max_chars_per_chunk": 8000,
            "request_timeout_sec": 10,
        },
    }
    defaults.update(overrides)
    return ApiCredentialConfig(**defaults)


VALID_SCRIPT_PAYLOAD = {
    "title": "Why Basque Cider Houses Pour From Above Your Head",
    "description": (
        "Sagardotegi cider is poured from a height for one measurable reason. "
        "Here is what the txotx ritual actually does to the liquid, and why the "
        "pour size is always small."
    ),
    "tags": ["basque cider", "sagardotegi", "txotx", "food travel", "cider"],
    "segments": [
        {
            "index": 1,
            "heading": "Cold open",
            "narration": "The cider hits the glass from a metre above, and that is not showmanship.",
            "visual_prompt": "Close-up of cider arcing into a wide glass in a dim stone cellar.",
            "target_duration_sec": 20,
        },
        {
            "index": 2,
            "heading": "Mechanism",
            "narration": "The long fall breaks the surface and releases dissolved carbon dioxide.",
            "visual_prompt": "Slow-motion macro of bubbles forming as liquid strikes glass.",
            "target_duration_sec": 25,
        },
        {
            "index": 3,
            "heading": "Payoff",
            "narration": "That is why the pour is small: the effect fades within a minute.",
            "visual_prompt": "Wide shot of a communal table, barrels lining the wall.",
            "target_duration_sec": 15,
        },
    ],
}


def openrouter_success_payload(content=None, *, prompt_tokens=1200, completion_tokens=800, cost=None):
    body = content if content is not None else json.dumps(VALID_SCRIPT_PAYLOAD)
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-test-123",
        "model": "anthropic/claude-sonnet-4.5",
        "choices": [{"message": {"role": "assistant", "content": body}, "finish_reason": "stop"}],
        "usage": usage,
    }


def moderation_payload(category_scores, *, flagged=False, moderation_id="modr-test-1"):
    categories = {key: score >= 0.5 for key, score in category_scores.items()}
    return {
        "id": moderation_id,
        "model": "omni-moderation-latest",
        "results": [
            {"flagged": flagged, "categories": categories, "category_scores": category_scores}
        ],
    }
