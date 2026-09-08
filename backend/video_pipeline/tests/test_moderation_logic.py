"""Moderation threshold logic, chunking and provider error mapping (FR-45, FR-48).

Pure logic — no DB, no network.
"""
from __future__ import annotations

import pytest
import requests

from moderation.models import ModerationVerdict
from providers.exceptions import (
    ProviderAuthError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderRetryableError,
    ProviderTimeoutError,
)
from video_pipeline.services.script_moderation import (
    OpenAIModerationClient,
    aggregate_category_scores,
    chunk_text,
    evaluate_scores,
    resolve_thresholds,
)
from video_pipeline.tests.fixtures import (
    FakeResponse,
    FakeSession,
    moderation_config,
    moderation_payload,
)


class TestEvaluateScores:
    def test_clean_content_passes(self):
        verdict, category, score = evaluate_scores({"violence": 0.01, "hate": 0.001})
        assert verdict == ModerationVerdict.PASS
        assert category == "violence"
        assert score == pytest.approx(0.01)

    def test_score_at_the_block_threshold_blocks(self):
        # Boundary: the SPEC says "chegaradan oshsa" -> >= is the safe reading.
        verdict, category, _ = evaluate_scores({"violence": 0.5}, block_threshold=0.5)
        assert verdict == ModerationVerdict.BLOCK
        assert category == "violence"

    def test_score_just_under_the_block_threshold_only_flags(self):
        verdict, _, _ = evaluate_scores({"violence": 0.49}, block_threshold=0.5, flag_threshold=0.2)
        assert verdict == ModerationVerdict.FLAG

    def test_score_under_both_thresholds_passes(self):
        verdict, _, _ = evaluate_scores({"violence": 0.19}, block_threshold=0.5, flag_threshold=0.2)
        assert verdict == ModerationVerdict.PASS

    def test_threshold_is_configurable(self):
        scores = {"violence": 0.3}
        assert evaluate_scores(scores, block_threshold=0.5)[0] == ModerationVerdict.FLAG
        assert evaluate_scores(scores, block_threshold=0.25)[0] == ModerationVerdict.BLOCK

    def test_per_category_threshold_overrides_the_global_one(self):
        scores = {"sexual/minors": 0.08}
        assert evaluate_scores(scores, block_threshold=0.5)[0] == ModerationVerdict.PASS
        verdict, category, _ = evaluate_scores(
            scores, block_threshold=0.5, flag_threshold=0.2, category_thresholds={"sexual/minors": 0.05}
        )
        assert verdict == ModerationVerdict.BLOCK
        assert category == "sexual/minors"

    def test_most_severe_category_wins_by_threshold_ratio(self):
        verdict, category, _ = evaluate_scores(
            {"violence": 0.55, "sexual/minors": 0.4},
            block_threshold=0.5,
            category_thresholds={"sexual/minors": 0.05},
        )
        assert verdict == ModerationVerdict.BLOCK
        # 0.4/0.05 = 8x over its threshold beats 0.55/0.5 = 1.1x.
        assert category == "sexual/minors"

    def test_provider_flag_escalates_even_when_scores_are_clean(self):
        verdict, _, _ = evaluate_scores({"violence": 0.01}, provider_flagged=True)
        assert verdict == ModerationVerdict.FLAG

    def test_provider_flag_never_downgrades_a_block(self):
        verdict, _, _ = evaluate_scores({"violence": 0.9}, provider_flagged=False)
        assert verdict == ModerationVerdict.BLOCK

    def test_non_numeric_scores_are_ignored_not_fatal(self):
        verdict, _, _ = evaluate_scores({"violence": None, "hate": "n/a", "sexual": 0.9})
        assert verdict == ModerationVerdict.BLOCK

    def test_empty_scores_pass(self):
        assert evaluate_scores({})[0] == ModerationVerdict.PASS


class TestResolveThresholds:
    def test_provider_config_overrides_settings(self, settings):
        settings.MODERATION_BLOCK_THRESHOLD = 0.9
        config = moderation_config()  # config JSON says 0.5
        assert resolve_thresholds(config)["block_threshold"] == 0.5

    def test_settings_used_when_config_is_silent(self, settings):
        settings.MODERATION_BLOCK_THRESHOLD = 0.77
        settings.MODERATION_FLAG_THRESHOLD = 0.11
        config = moderation_config(config={})
        thresholds = resolve_thresholds(config)
        assert thresholds["block_threshold"] == 0.77
        assert thresholds["flag_threshold"] == 0.11
        assert thresholds["category_thresholds"] == {}


class TestChunking:
    def test_short_text_is_a_single_chunk(self):
        assert chunk_text("short script", 8000) == ["short script"]

    def test_empty_text_yields_no_chunks(self):
        assert chunk_text("", 8000) == []
        assert chunk_text("   ", 8000) == []

    def test_splits_on_paragraph_boundaries(self):
        text = "\n\n".join(["a" * 40 for _ in range(10)])
        chunks = chunk_text(text, 100)
        assert len(chunks) > 1
        assert all(len(c) <= 100 for c in chunks)
        # No content is lost.
        assert "".join(chunks).replace("\n", "") == text.replace("\n", "")

    def test_oversized_single_paragraph_is_hard_split(self):
        chunks = chunk_text("z" * 250, 100)
        assert [len(c) for c in chunks] == [100, 100, 50]


class TestAggregateAcrossChunks:
    def test_takes_the_worst_score_per_category(self):
        results = [
            {"flagged": False, "category_scores": {"violence": 0.1, "hate": 0.4}},
            {"flagged": False, "category_scores": {"violence": 0.7, "hate": 0.2}},
        ]
        scores, flagged = aggregate_category_scores(results)
        assert scores == {"violence": 0.7, "hate": 0.4}
        assert flagged is False

    def test_any_flagged_chunk_flags_the_whole_script(self):
        results = [
            {"flagged": False, "category_scores": {"violence": 0.01}},
            {"flagged": True, "category_scores": {"violence": 0.02}},
        ]
        _, flagged = aggregate_category_scores(results)
        assert flagged is True


class TestModerationClient:
    def make(self, responses, config=None):
        config = config or moderation_config()
        session = FakeSession(responses)
        return OpenAIModerationClient(config, api_key="test-key", session=session), session

    def test_sends_model_and_chunk_array(self):
        client, session = self.make([FakeResponse(200, moderation_payload({"violence": 0.01}))])
        client.moderate(["a", "b"])
        body = session.calls[0]["json"]
        assert body["model"] == "omni-moderation-latest"
        assert body["input"] == ["a", "b"]
        assert session.calls[0]["timeout"] == 10

    def test_empty_input_is_a_permanent_error(self):
        client, _ = self.make([])
        with pytest.raises(ProviderPermanentError):
            client.moderate([])

    def test_429_is_retryable(self):
        client, _ = self.make([FakeResponse(429, {}, headers={"Retry-After": "7"})])
        with pytest.raises(ProviderRateLimitError) as exc_info:
            client.moderate(["x"])
        assert exc_info.value.retry_after_sec == 7

    def test_500_is_retryable(self):
        client, _ = self.make([FakeResponse(503, {})])
        with pytest.raises(ProviderRetryableError):
            client.moderate(["x"])

    def test_timeout_is_retryable(self):
        client, _ = self.make([requests.exceptions.Timeout()])
        with pytest.raises(ProviderTimeoutError):
            client.moderate(["x"])

    def test_401_is_permanent(self):
        client, _ = self.make([FakeResponse(401, {})])
        with pytest.raises(ProviderAuthError):
            client.moderate(["x"])

    def test_missing_results_array_is_a_response_error(self):
        client, _ = self.make([FakeResponse(200, {"id": "x"})])
        with pytest.raises(ProviderResponseError):
            client.moderate(["x"])

    def test_empty_results_array_is_a_response_error(self):
        client, _ = self.make([FakeResponse(200, {"id": "x", "results": []})])
        with pytest.raises(ProviderResponseError):
            client.moderate(["x"])
