"""Cost computation and secret resolution (FR-51, FR-84, C-5). No DB, no network."""
from __future__ import annotations

from decimal import Decimal

import pytest

from providers.exceptions import ProviderNotConfigured
from providers.models import CostUnit
from providers.services import compute_token_cost, resolve_api_key
from video_pipeline.tests.fixtures import llm_config, moderation_config


class TestComputeTokenCost:
    def test_uses_split_input_output_prices(self):
        # 1200 in @ $0.003/1k + 800 out @ $0.015/1k = 0.0036 + 0.012 = 0.0156
        cost = compute_token_cost(llm_config(), prompt_tokens=1200, completion_tokens=800)
        assert cost == Decimal("0.015600")

    def test_provider_reported_cost_wins_over_the_local_price_table(self):
        cost = compute_token_cost(
            llm_config(),
            prompt_tokens=1200,
            completion_tokens=800,
            provider_reported_cost="0.009",
        )
        assert cost == Decimal("0.009000")

    def test_provider_reported_zero_is_honoured_not_treated_as_missing(self):
        cost = compute_token_cost(
            llm_config(), prompt_tokens=1000, completion_tokens=1000, provider_reported_cost=0
        )
        assert cost == Decimal("0.000000")

    def test_falls_back_to_flat_per_1k_rate_when_split_prices_are_absent(self):
        config = llm_config(config={})  # no input/output split, unit_cost_usd = 0.015
        cost = compute_token_cost(config, prompt_tokens=1000, completion_tokens=1000)
        assert cost == Decimal("0.030000")

    def test_per_request_pricing(self):
        config = moderation_config(unit_cost_usd=Decimal("0.002"), cost_unit=CostUnit.PER_REQUEST)
        assert compute_token_cost(config, prompt_tokens=0, completion_tokens=0) == Decimal("0.002000")

    def test_unpriced_provider_reports_zero_rather_than_crashing(self):
        config = llm_config(config={}, unit_cost_usd=None, cost_unit="")
        assert compute_token_cost(config, prompt_tokens=999, completion_tokens=999) == Decimal("0")

    def test_malformed_price_in_config_is_ignored(self):
        config = llm_config(
            config={"input_cost_per_1k_usd": "not-a-number", "output_cost_per_1k_usd": "0.015"}
        )
        # Falls through to the flat per-1k rate instead of raising.
        assert compute_token_cost(config, prompt_tokens=1000, completion_tokens=0) == Decimal("0.015000")

    def test_rounding_is_half_up_at_six_decimal_places(self):
        config = llm_config(
            config={"input_cost_per_1k_usd": "0.0000005", "output_cost_per_1k_usd": "0"}
        )
        assert compute_token_cost(config, prompt_tokens=1000, completion_tokens=0) == Decimal("0.000001")


class TestSecretResolution:
    """C-5 / FR-84: the DB stores the NAME of the env var, never the key."""

    def test_secret_ref_is_dereferenced_from_settings(self, settings):
        settings.OPENROUTER_API_KEY = "sk-or-test"
        assert resolve_api_key(llm_config()) == "sk-or-test"

    def test_empty_secret_raises_a_configuration_error(self, settings):
        settings.OPENROUTER_API_KEY = ""
        with pytest.raises(ProviderNotConfigured):
            resolve_api_key(llm_config())

    def test_env_var_is_used_when_the_setting_is_absent(self, monkeypatch, settings):
        config = llm_config(secret_ref="SOME_PROVIDER_KEY_NOT_IN_SETTINGS")
        monkeypatch.setenv("SOME_PROVIDER_KEY_NOT_IN_SETTINGS", "env-value")
        assert resolve_api_key(config) == "env-value"

    def test_no_secret_ref_at_all_raises(self):
        with pytest.raises(ProviderNotConfigured):
            resolve_api_key(llm_config(secret_ref=""))

    def test_config_repr_does_not_contain_key_material(self, settings):
        settings.OPENROUTER_API_KEY = "sk-or-super-secret"
        config = llm_config()
        assert "sk-or-super-secret" not in str(config)
        assert "sk-or-super-secret" not in repr(config.config)
