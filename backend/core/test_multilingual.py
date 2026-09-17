"""Regression coverage for the multilingual API and encrypted persisted tokens."""

from types import SimpleNamespace
from datetime import datetime, time, timezone as dt_timezone

import pytest
from cryptography.fernet import Fernet, InvalidToken
from django.test import override_settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from accounts.tests.factories import UserFactory
from content_planning.serializers import ContentPreferenceSerializer
from content_planning.services import next_publish_slot
from core.crypto import decrypt_value, encrypt_value
from core.languages import LANGUAGE_CODES, normalize_language
from providers.language_routing import select_tts_config, supports_language
from providers.models import ApiCredentialConfig
from providers.exceptions import ProviderNotConfigured


def test_authenticated_catalog_contains_thirty_canonical_locales():
    client = APIClient()
    client.force_authenticate(SimpleNamespace(is_authenticated=True, pk="catalog-test"))
    response = client.get(reverse("channels:content-languages"))
    assert response.status_code == 200
    assert response.data["default"] == "ru"
    assert len({row["code"] for row in response.data["languages"]}) == 30


@pytest.mark.parametrize("code", LANGUAGE_CODES)
def test_content_language_validation_accepts_each_locale(code):
    assert ContentPreferenceSerializer().validate_language(code) == code


def test_locale_normalization_preserves_region():
    assert normalize_language(" AR_eg ") == "ar-EG"
    with pytest.raises(ValueError):
        normalize_language("Pakistan")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/2fa/enable",
        "/api/v1/auth/2fa/verify",
        "/api/v1/auth/2fa/login",
        "/api/v1/me/sessions",
        "/api/v1/me/data/export",
        "/api/v1/me/data/delete",
    ],
)
def test_account_routes_are_real_and_require_credentials(path):
    view = resolve(path).func.view_class
    assert view.__name__ != "NotImplementedStubView"
    response = (
        APIClient().post(path)
        if path != "/api/v1/me/sessions"
        else APIClient().get(path)
    )
    assert response.status_code in (400, 401, 403)


def test_aes_random_nonce_tamper_detection_legacy_and_rotation():
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    with override_settings(
        FIELD_ENCRYPTION_KEYS_RAW=f"1:{old}", FIELD_ENCRYPTION_ACTIVE_KEY_VERSION=1
    ):
        encrypted = encrypt_value("O‘zbekcha العربية 中文")
        assert encrypted.startswith(b"AYG1")
        assert encrypted != encrypt_value("O‘zbekcha العربية 中文")
        assert decrypt_value(encrypted) == "O‘zbekcha العربية 中文"
        damaged = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
        with pytest.raises(InvalidToken):
            decrypt_value(damaged)
        legacy = Fernet(old.encode()).encrypt(b"existing-token")
        assert decrypt_value(legacy) == "existing-token"
    with override_settings(
        FIELD_ENCRYPTION_KEYS_RAW=f"2:{new},1:{old}",
        FIELD_ENCRYPTION_ACTIVE_KEY_VERSION=2,
    ):
        assert decrypt_value(encrypted) == "O‘zbekcha العربية 中文"
        assert decrypt_value(legacy) == "existing-token"
        assert encrypt_value("new")[4:8] == b"\0\0\0\2"
    with override_settings(
        FIELD_ENCRYPTION_KEYS_RAW=f"2:{new}", FIELD_ENCRYPTION_ACTIVE_KEY_VERSION=2
    ):
        with pytest.raises(InvalidToken):
            decrypt_value(encrypted)


def test_tts_capabilities_do_not_claim_unknown_models_or_dialects():
    cfg = ApiCredentialConfig(
        provider="elevenlabs", model_name="eleven_multilingual_v2"
    )
    assert supports_language(cfg, "en")
    assert not supports_language(cfg, "uz")
    assert not supports_language(cfg, "ar-EG")
    cfg.model_name = "eleven_v3"
    assert supports_language(cfg, "ky")
    assert not supports_language(cfg, "tk")
    cfg.config = {"supported_languages": ["ar-EG"]}
    assert supports_language(cfg, "ar-EG")
    assert not supports_language(cfg, "en")


@pytest.mark.django_db
def test_provider_routing_chooses_language_specific_active_provider():
    ApiCredentialConfig.objects.filter(service="tts").delete()
    ApiCredentialConfig.objects.create(
        service="tts",
        provider="elevenlabs",
        model_name="eleven_multilingual_v2",
        is_primary=True,
    )
    azure = ApiCredentialConfig.objects.create(
        service="tts", provider="azure_tts", config={"supported_languages": ["uz"]}
    )
    assert select_tts_config("uz") == azure
    with pytest.raises(ProviderNotConfigured):
        select_tts_config("tk")


@pytest.mark.django_db
@pytest.mark.parametrize("code", LANGUAGE_CODES)
def test_profile_can_persist_every_ui_locale(code):
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user)
    response = client.patch("/api/v1/me", {"locale": code}, format="json")
    assert response.status_code == 200, response.data
    user.refresh_from_db()
    assert user.locale == code


def test_schedule_utc_conversion_works_on_django_5():
    preference = SimpleNamespace(
        publish_timezone="Asia/Tashkent",
        publish_time_local=time(12),
        frequency="daily",
        publish_days=None,
    )
    result = next_publish_slot(
        preference, now=datetime(2026, 9, 17, 6, tzinfo=dt_timezone.utc)
    )
    assert result.hour == 7
    assert result.utcoffset().total_seconds() == 0


def test_cjk_duration_does_not_depend_on_spaces():
    from video_pipeline.services.script_generation import _estimate_seconds_from_text

    assert _estimate_seconds_from_text("今天我们学习人工智能" * 10) > 10
    assert _estimate_seconds_from_text("word " * 150) == 60


def test_language_specific_font_override(tmp_path):
    from video_pipeline.services.language_fonts import font_for_language

    font = tmp_path / "arabic.ttf"
    font.write_bytes(b"test-font")
    with override_settings(ASSEMBLY_LANGUAGE_FONTS={"ar-EG": str(font)}):
        assert font_for_language("ar-EG") == str(font)
