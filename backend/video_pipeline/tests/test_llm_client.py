"""OpenRouter client: request shape, response parsing and the retryable vs
permanent error split (NFR-24, NFR-38 — no real network call anywhere).
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest
import requests

from providers.exceptions import (
    ProviderAuthError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderRetryableError,
    ProviderTimeoutError,
)
from video_pipeline.services.llm_client import OpenRouterClient
from video_pipeline.tests.fixtures import (
    FakeResponse,
    FakeSession,
    llm_config,
    openrouter_success_payload,
)


def make_client(responses, config=None):
    config = config or llm_config()
    session = FakeSession(responses)
    client = OpenRouterClient(config, api_key="test-key-not-a-real-secret", session=session)
    return client, session


class TestRequestShape:
    def test_model_comes_from_config_not_from_code(self):
        config = llm_config(model_name="anthropic/claude-opus-4.1")
        client, session = make_client([FakeResponse(200, openrouter_success_payload())], config)
        client.chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert session.calls[0]["json"]["model"] == "anthropic/claude-opus-4.1"

    def test_json_mode_and_usage_accounting_are_requested(self):
        client, session = make_client([FakeResponse(200, openrouter_success_payload())])
        client.chat_completion(messages=[{"role": "user", "content": "hi"}])
        body = session.calls[0]["json"]
        assert body["response_format"] == {"type": "json_object"}
        assert body["usage"] == {"include": True}

    def test_json_mode_can_be_disabled_per_config(self):
        config = llm_config(config={**llm_config().config, "json_mode": False})
        client, session = make_client([FakeResponse(200, openrouter_success_payload())], config)
        client.chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert "response_format" not in session.calls[0]["json"]

    def test_timeout_and_token_cap_come_from_config(self):
        client, session = make_client([FakeResponse(200, openrouter_success_payload())])
        client.chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert session.calls[0]["timeout"] == 30
        assert session.calls[0]["json"]["max_tokens"] == 1000

    def test_api_key_is_only_ever_in_the_authorization_header(self):
        """NFR-3: the key must not leak into the body or any other header."""
        client, session = make_client([FakeResponse(200, openrouter_success_payload())])
        client.chat_completion(messages=[{"role": "user", "content": "hi"}])
        call = session.calls[0]
        assert call["headers"]["Authorization"] == "Bearer test-key-not-a-real-secret"
        assert "test-key-not-a-real-secret" not in json.dumps(call["json"])
        other_headers = {k: v for k, v in call["headers"].items() if k != "Authorization"}
        assert "test-key-not-a-real-secret" not in json.dumps(other_headers)

    def test_empty_model_name_is_a_configuration_error(self):
        with pytest.raises(ProviderPermanentError):
            OpenRouterClient(llm_config(model_name=""), api_key="k", session=FakeSession([]))


class TestResponseParsing:
    def test_extracts_content_tokens_and_request_id(self):
        client, _ = make_client([FakeResponse(200, openrouter_success_payload())])
        result = client.chat_completion(messages=[])
        assert json.loads(result.content)["title"]
        assert result.prompt_tokens == 1200
        assert result.completion_tokens == 800
        assert result.total_tokens == 2000
        assert result.request_id == "gen-test-123"
        assert result.finish_reason == "stop"
        assert result.http_status == 200
        assert result.latency_ms >= 0

    def test_provider_reported_cost_is_captured(self):
        client, _ = make_client([FakeResponse(200, openrouter_success_payload(cost=0.0123))])
        assert client.chat_completion(messages=[]).provider_cost_usd == Decimal("0.0123")

    def test_missing_usage_block_defaults_to_zero_tokens(self):
        payload = openrouter_success_payload()
        payload.pop("usage")
        client, _ = make_client([FakeResponse(200, payload)])
        result = client.chat_completion(messages=[])
        assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (0, 0, 0)

    def test_empty_choices_raises_response_error(self):
        client, _ = make_client([FakeResponse(200, {"id": "x", "choices": []})])
        with pytest.raises(ProviderResponseError):
            client.chat_completion(messages=[])

    def test_empty_content_raises_response_error(self):
        payload = openrouter_success_payload(content="   ")
        client, _ = make_client([FakeResponse(200, payload)])
        with pytest.raises(ProviderResponseError):
            client.chat_completion(messages=[])

    def test_error_envelope_with_http_200_is_detected(self):
        client, _ = make_client([FakeResponse(200, {"error": {"code": 400, "message": "bad"}})])
        with pytest.raises(ProviderResponseError):
            client.chat_completion(messages=[])

    def test_non_json_body_raises_response_error(self):
        client, _ = make_client([FakeResponse(200, text_body="<html>502 Bad Gateway</html>")])
        with pytest.raises(ProviderResponseError):
            client.chat_completion(messages=[])


class TestErrorClassification:
    """The split that decides whether Celery retries or fails the job."""

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_5xx_is_retryable(self, status):
        client, _ = make_client([FakeResponse(status, {})])
        with pytest.raises(ProviderRetryableError):
            client.chat_completion(messages=[])

    def test_429_is_retryable_and_carries_retry_after(self):
        client, _ = make_client([FakeResponse(429, {}, headers={"Retry-After": "42"})])
        with pytest.raises(ProviderRateLimitError) as exc_info:
            client.chat_completion(messages=[])
        assert exc_info.value.retry_after_sec == 42
        assert exc_info.value.error_code == "provider_rate_limited"

    def test_429_without_retry_after_header_is_still_retryable(self):
        client, _ = make_client([FakeResponse(429, {})])
        with pytest.raises(ProviderRateLimitError) as exc_info:
            client.chat_completion(messages=[])
        assert exc_info.value.retry_after_sec is None

    def test_timeout_is_retryable(self):
        client, _ = make_client([requests.exceptions.Timeout("timed out")])
        with pytest.raises(ProviderTimeoutError):
            client.chat_completion(messages=[])

    def test_connection_error_is_retryable(self):
        client, _ = make_client([requests.exceptions.ConnectionError("refused")])
        with pytest.raises(ProviderRetryableError):
            client.chat_completion(messages=[])

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_failures_are_permanent(self, status):
        client, _ = make_client([FakeResponse(status, {})])
        with pytest.raises(ProviderAuthError) as exc_info:
            client.chat_completion(messages=[])
        assert not isinstance(exc_info.value, ProviderRetryableError)

    def test_402_out_of_credit_is_permanent(self):
        client, _ = make_client([FakeResponse(402, {})])
        with pytest.raises(ProviderPermanentError) as exc_info:
            client.chat_completion(messages=[])
        assert exc_info.value.error_code == "provider_insufficient_credit"

    def test_400_is_permanent(self):
        client, _ = make_client([FakeResponse(400, {})])
        with pytest.raises(ProviderPermanentError):
            client.chat_completion(messages=[])

    def test_error_messages_never_echo_the_response_body(self):
        """NFR-3: bodies can contain prompt/user data — only the status is quoted."""
        client, _ = make_client(
            [FakeResponse(400, {"error": {"message": "sk-super-secret-leaked-token"}})]
        )
        with pytest.raises(ProviderPermanentError) as exc_info:
            client.chat_completion(messages=[])
        assert "sk-super-secret-leaked-token" not in str(exc_info.value)
