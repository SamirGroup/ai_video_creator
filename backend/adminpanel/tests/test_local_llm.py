from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from accounts.tests.factories import UserFactory
from django.core.cache import cache
from django.core.management import call_command
from providers.exceptions import (
    ProviderNotConfigured,
    ProviderPermanentError,
    ProviderResponseError,
)
from providers.models import ApiCredentialConfig
from providers.services import ensure_provider_ready
from rest_framework.test import APIClient
from video_pipeline.services.llm_client import get_llm_client
from video_pipeline.services.ollama_client import OllamaClient
from video_pipeline.tests.fixtures import FakeResponse, llm_config


def test_local_transport_ignores_database_endpoint_and_keys(settings):
    settings.OLLAMA_BASE_URL = "http://127.0.0.1:11434"
    settings.OLLAMA_API_KEY = ""
    config = llm_config(provider="ollama", model_name="qwen3:4b-instruct")
    config.config["base_url"] = "https://untrusted.example"
    session = Mock()
    session.post.return_value = FakeResponse(
        payload={
            "message": {"content": '{"ok":true}'},
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 5,
            "done_reason": "stop",
        }
    )
    ensure_provider_ready(config)
    result = get_llm_client(config, session=session).chat_completion(
        messages=[{"role": "user", "content": "Return JSON"}], max_tokens=80
    )
    assert result.provider_cost_usd == Decimal(0)
    assert result.total_tokens == 15
    args, kwargs = session.post.call_args
    assert args[0] == "http://127.0.0.1:11434/api/chat"
    assert "Authorization" not in kwargs["headers"]
    assert kwargs["json"]["format"] == "json"
    assert kwargs["json"]["stream"] is False and kwargs["json"]["think"] is False
    assert kwargs["allow_redirects"] is False


def test_missing_endpoint_and_oversized_context_fail_before_network(settings):
    settings.OLLAMA_BASE_URL = ""
    config = llm_config(provider="ollama")
    with pytest.raises(ProviderNotConfigured):
        ensure_provider_ready(config)
    settings.OLLAMA_BASE_URL = "http://localhost:11434"
    session = Mock()
    with pytest.raises(ProviderPermanentError):
        OllamaClient(config, session=session).chat_completion(
            messages=[{"role": "user", "content": "x" * 20000}]
        )
    session.post.assert_not_called()


def test_truncated_output_rejected(settings):
    settings.OLLAMA_BASE_URL = "http://localhost:11434"
    session = Mock()
    session.post.return_value = FakeResponse(
        payload={
            "message": {"content": "partial"},
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 5,
            "done_reason": "length",
        }
    )
    with pytest.raises(ProviderResponseError):
        OllamaClient(llm_config(), session=session).chat_completion(
            messages=[{"role": "user", "content": "hello"}]
        )


@pytest.mark.django_db
def test_local_activation_requires_success_and_current_endpoint(settings):
    settings.OLLAMA_BASE_URL = "http://localhost:11434"
    cache.clear()
    call_command("seed_local_llm")
    config = ApiCredentialConfig.objects.get(provider="ollama")
    assert not config.is_active and not config.is_primary
    client = APIClient()
    client.force_authenticate(UserFactory(is_superuser=True, is_totp_enabled=True))
    url = "/api/v1/admin/local-llm"
    assert client.post(url, {"action": "activate"}, format="json").status_code == 400
    with patch("adminpanel.local_llm.OllamaClient") as cls:
        cls.return_value.chat_completion.return_value = Mock(
            content='{"ok":true}', total_tokens=12, prompt_tokens=8, completion_tokens=4
        )
        response = client.post(url, {"action": "test"}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["verified"]
    settings.OLLAMA_BASE_URL = "http://other-private-host:11434"
    assert client.post(url, {"action": "activate"}, format="json").status_code == 400
    settings.OLLAMA_BASE_URL = "http://localhost:11434"
    cache.clear()
    response = client.post(url, {"action": "activate"}, format="json")
    assert response.status_code == 200 and response.data["active"]
    client.force_authenticate(UserFactory())
    assert client.post(url, {"action": "test"}, format="json").status_code == 403
