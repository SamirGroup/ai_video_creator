from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from accounts.tests.factories import UserFactory
from django.core.cache import cache
from django.db import connection
from providers.exceptions import ProviderAuthError
from providers.models import ApiCredentialConfig, ProviderSecret
from rest_framework.test import APIClient
from video_pipeline.services.anthropic_client import AnthropicClient
from video_pipeline.services.llm_client import get_llm_client
from video_pipeline.tests.fixtures import FakeResponse, llm_config


def test_direct_request_and_accounting():
    session = Mock()
    session.request.return_value = FakeResponse(
        payload={
            "content": [{"type": "text", "text": '{"ok":true}'}],
            "usage": {"input_tokens": 100, "output_tokens": 20},
            "id": "msg_test",
        }
    )
    client = get_llm_client(
        llm_config(provider="anthropic", model_name="claude-sonnet-4-5"),
        api_key="fake",
        session=session,
    )
    assert isinstance(client, AnthropicClient)
    result = client.chat_completion(
        messages=[
            {"role": "system", "content": "Plan"},
            {"role": "user", "content": "Hello"},
        ]
    )
    args, kwargs = session.request.call_args
    assert args == ("POST", "https://api.anthropic.com/v1/messages")
    assert kwargs["allow_redirects"] is False
    assert kwargs["headers"]["x-api-key"] == "fake"
    assert len(kwargs["json"]["messages"]) == 1
    assert "valid JSON" in kwargs["json"]["system"]
    assert result.provider_cost_usd == Decimal(".0006")
    assert result.total_tokens == 120


def test_auth_errors_never_include_provider_body():
    session = Mock()
    session.request.return_value = FakeResponse(401, {"error": "secret-value"})
    with pytest.raises(ProviderAuthError) as error:
        AnthropicClient(llm_config(), api_key="fake", session=session).check_model()
    assert "secret-value" not in str(error.value)


@pytest.mark.django_db
def test_secure_save_test_activate_flow():
    cache.clear()
    client = APIClient()
    client.force_authenticate(UserFactory(is_superuser=True, is_totp_enabled=True))
    url = "/api/v1/admin/anthropic"
    payload = {
        "action": "save",
        "api_key": "sk-ant-test-only-not-real",
        "model": "claude-sonnet-4-5",
        "input_per_million": "3",
        "output_per_million": "15",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 200, response.data
    assert payload["api_key"] not in str(response.data)
    config = ApiCredentialConfig.objects.get(provider="anthropic")
    assert not config.is_active
    secret = ProviderSecret.objects.get(provider_config=config)
    assert secret.value_enc == payload["api_key"]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT value_enc FROM providers_providersecret WHERE id = %s", [secret.pk]
        )
        assert payload["api_key"].encode() not in bytes(cursor.fetchone()[0])
    assert client.post(url, {"action": "activate"}, format="json").status_code == 400
    with patch("adminpanel.anthropic_config.AnthropicClient") as cls:
        cls.return_value.chat_completion.return_value = Mock(
            total_tokens=5,
            prompt_tokens=3,
            completion_tokens=2,
            provider_cost_usd=Decimal(".000039"),
            request_id="test",
        )
        response = client.post(url, {"action": "test"}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["verified"]
    response = client.post(url, {"action": "activate"}, format="json")
    assert response.status_code == 200, response.data
    config.refresh_from_db()
    assert config.is_active and config.is_primary
    assert config.resolve_secret() == payload["api_key"]
    cache.clear()
    response = client.post(
        url, {**payload, "api_key": "sk-ant-new-test-key"}, format="json"
    )
    assert not response.data["verified"] and not response.data["active"]


@pytest.mark.django_db
def test_non_superadmin_and_no_2fa_cannot_store_keys():
    cache.clear()
    client = APIClient()
    for user in [UserFactory(), UserFactory(is_superuser=True, is_totp_enabled=False)]:
        client.force_authenticate(user)
        assert (
            client.post(
                "/api/v1/admin/anthropic", {"action": "save"}, format="json"
            ).status_code
            == 403
        )
    assert not ProviderSecret.objects.exists()
