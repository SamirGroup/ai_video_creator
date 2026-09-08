"""YouTube OAuth flow tests (FR-10..FR-17, NFR-4).

Google is never called for real: `google_auth_oauthlib.flow.Flow` and the
`channels.services` functions that wrap the YouTube Data API are mocked, per
NFR-38 ("Barcha tashqi provider'lar test muhitida mock/stub bilan; CI real
API chaqirmaydi"). What IS tested for real: state/PKCE one-time-use
enforcement (NFR-4), the FR-16 one-channel-per-account uniqueness guard, and
that tokens are never echoed back in an API response (C-5).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.tests.factories import UserFactory
from channels import services
from channels.models import ConnectionStatus, YouTubeChannel

pytestmark = pytest.mark.django_db

# NFR-4's `state` store lives in Django's cache; tests use LocMemCache instead
# of the Redis backend configured for dev/prod so they never need a running
# Redis instance.
LOCMEM_CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@pytest.fixture(autouse=True)
def _locmem_cache():
    with override_settings(CACHES=LOCMEM_CACHES):
        cache.clear()
        yield
        cache.clear()


@pytest.fixture
def authed_client():
    user = UserFactory(email="creator@example.com")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


def _fake_flow(auth_url="https://accounts.google.com/o/oauth2/auth?fake=1"):
    flow = MagicMock()
    flow.authorization_url.return_value = (auth_url, "ignored-by-us")
    return flow


class TestYouTubeAuthorize:
    def test_authorize_requires_authentication(self):
        response = APIClient().get(reverse("channels:youtube-authorize"))
        assert response.status_code == 401

    def test_authorize_returns_authorization_url_and_registers_state(self, authed_client):
        client, _user = authed_client

        with patch("channels.services.Flow.from_client_config", return_value=_fake_flow()):
            response = client.get(reverse("channels:youtube-authorize"))

        assert response.status_code == 200
        assert response.data["authorization_url"].startswith("https://accounts.google.com")
        state = response.data["state"]
        assert cache.get(f"oauth:youtube:state:{state}") is not None  # NFR-4


class TestYouTubeCallback:
    def _seed_state(self, user, *, scopes=None):
        with patch("channels.services.Flow.from_client_config", return_value=_fake_flow()):
            _, state = services.build_authorization_request(
                kind="youtube",
                user_id=user.id,
                scopes=scopes or services.YOUTUBE_SCOPES,
                redirect_uri="http://localhost:8000/api/v1/oauth/youtube/callback",
            )
        return state

    def test_callback_rejects_missing_code_or_state(self, authed_client):
        client, _user = authed_client
        response = client.get(reverse("channels:youtube-callback"), {"code": "abc"})
        assert response.status_code == 400

    def test_callback_rejects_unknown_or_expired_state(self, authed_client):
        client, _user = authed_client
        response = client.get(
            reverse("channels:youtube-callback"), {"code": "abc", "state": "does-not-exist"}
        )
        assert response.status_code == 400

    def test_callback_rejects_state_issued_for_a_different_user(self, authed_client):
        client, _user = authed_client
        other_user = UserFactory(email="other@example.com")
        state = self._seed_state(other_user)

        response = client.get(reverse("channels:youtube-callback"), {"code": "abc", "state": state})

        assert response.status_code == 400

    def test_callback_surfaces_google_denied_error(self, authed_client):
        client, _user = authed_client
        response = client.get(
            reverse("channels:youtube-callback"), {"error": "access_denied", "state": "whatever"}
        )
        assert response.status_code == 400

    def test_callback_exchanges_code_and_persists_channel(self, authed_client):
        client, user = authed_client
        state = self._seed_state(user)
        fake_credentials = MagicMock(token="access-token-123", refresh_token="refresh-token-456", expiry=None)
        channel_payload = {
            "id": "UC_test_channel_id",
            "snippet": {"title": "My Channel", "customUrl": "@mychannel", "thumbnails": {}},
            "statistics": {"subscriberCount": "1000", "videoCount": "42"},
        }

        with patch("channels.services.exchange_code_for_credentials", return_value=fake_credentials), patch(
            "channels.services.fetch_own_channel", return_value=channel_payload
        ):
            response = client.get(reverse("channels:youtube-callback"), {"code": "auth-code", "state": state})

        assert response.status_code == 201
        channel = YouTubeChannel.objects.get(user=user, youtube_channel_id="UC_test_channel_id")
        assert channel.status == ConnectionStatus.CONNECTED
        assert channel.channel_title == "My Channel"
        assert channel.subscriber_count == 1000
        # C-5 / NFR-2: tokens are never echoed back in any API response.
        assert "access_token" not in response.data
        assert "refresh_token" not in response.data
        assert "access_token_enc" not in response.data

    def test_callback_state_is_single_use(self, authed_client):
        client, user = authed_client
        state = self._seed_state(user)
        fake_credentials = MagicMock(token="t", refresh_token="r", expiry=None)
        channel_payload = {"id": "UC_reuse", "snippet": {}, "statistics": {}}

        with patch("channels.services.exchange_code_for_credentials", return_value=fake_credentials), patch(
            "channels.services.fetch_own_channel", return_value=channel_payload
        ):
            first = client.get(reverse("channels:youtube-callback"), {"code": "auth-code", "state": state})
            second = client.get(reverse("channels:youtube-callback"), {"code": "auth-code", "state": state})

        assert first.status_code == 201
        assert second.status_code == 400

    def test_callback_maps_invalid_grant_to_400_without_creating_a_channel(self, authed_client):
        client, user = authed_client
        state = self._seed_state(user)

        with patch(
            "channels.services.exchange_code_for_credentials",
            side_effect=services.OAuthExchangeError("invalid_grant"),
        ):
            response = client.get(reverse("channels:youtube-callback"), {"code": "bad-code", "state": state})

        assert response.status_code == 400
        assert not YouTubeChannel.objects.filter(user=user).exists()

    def test_callback_rejects_channel_already_linked_to_another_user(self, authed_client):
        client, user = authed_client
        other_user = UserFactory(email="owner@example.com")
        YouTubeChannel.objects.create(
            user=other_user, youtube_channel_id="UC_taken", status=ConnectionStatus.CONNECTED
        )
        state = self._seed_state(user)
        fake_credentials = MagicMock(token="t", refresh_token="r", expiry=None)
        channel_payload = {"id": "UC_taken", "snippet": {}, "statistics": {}}

        with patch("channels.services.exchange_code_for_credentials", return_value=fake_credentials), patch(
            "channels.services.fetch_own_channel", return_value=channel_payload
        ):
            response = client.get(reverse("channels:youtube-callback"), {"code": "auth-code", "state": state})

        assert response.status_code == 409


class TestYouTubeRevoke:
    def test_revoke_requires_a_connected_channel(self, authed_client):
        client, _user = authed_client
        response = client.post(reverse("channels:youtube-revoke"))
        assert response.status_code == 404

    def test_revoke_calls_google_and_hard_deletes_tokens(self, authed_client):
        client, user = authed_client
        channel = YouTubeChannel.objects.create(
            user=user,
            youtube_channel_id="UC_to_revoke",
            status=ConnectionStatus.CONNECTED,
            access_token_enc="access-token",
            refresh_token_enc="refresh-token",
        )

        with patch("channels.services.revoke_google_token", return_value=True) as mock_revoke:
            response = client.post(reverse("channels:youtube-revoke"))

        assert response.status_code == 200
        mock_revoke.assert_called_once()
        channel.refresh_from_db()
        assert channel.status == ConnectionStatus.DISCONNECTED
        assert channel.access_token_enc is None
        assert channel.refresh_token_enc is None


class TestChannelDisconnectEndpoint:
    def test_delete_disconnects_owned_channel(self, authed_client):
        client, user = authed_client
        channel = YouTubeChannel.objects.create(
            user=user,
            youtube_channel_id="UC_delete_me",
            status=ConnectionStatus.CONNECTED,
            access_token_enc="access-token",
            refresh_token_enc="refresh-token",
        )

        with patch("channels.services.revoke_google_token", return_value=True):
            response = client.delete(reverse("channels:channel-detail", args=[channel.id]))

        assert response.status_code == 204
        channel.refresh_from_db()
        assert channel.status == ConnectionStatus.DISCONNECTED
        assert channel.access_token_enc is None

    def test_delete_returns_404_for_another_users_channel(self, authed_client):
        client, _user = authed_client
        other_user = UserFactory(email="another@example.com")
        channel = YouTubeChannel.objects.create(user=other_user, youtube_channel_id="UC_not_mine")

        response = client.delete(reverse("channels:channel-detail", args=[channel.id]))

        assert response.status_code == 404


class TestTokenRefresh:
    """FR-14: refresh_channel_credentials — the function a Celery Beat task
    (channels/tasks.py) calls before token expiry.
    """

    def test_successful_refresh_updates_stored_token(self, authed_client):
        _client, user = authed_client
        channel = YouTubeChannel.objects.create(
            user=user,
            youtube_channel_id="UC_refresh_ok",
            status=ConnectionStatus.CONNECTED,
            access_token_enc="old-token",
            refresh_token_enc="refresh-token",
        )

        def _fake_refresh(self, request):
            self.token = "new-token"

        with patch("channels.services.Credentials.refresh", new=_fake_refresh):
            result = services.refresh_channel_credentials(channel)

        assert result is True
        channel.refresh_from_db()
        assert channel.access_token_enc == "new-token"
        assert channel.status == ConnectionStatus.CONNECTED

    def test_invalid_grant_disconnects_channel_and_pauses_preferences(self, authed_client):
        from google.auth.exceptions import RefreshError

        from content_planning.models import ContentPreference

        _client, user = authed_client
        channel = YouTubeChannel.objects.create(
            user=user,
            youtube_channel_id="UC_refresh_fail",
            status=ConnectionStatus.CONNECTED,
            access_token_enc="old-token",
            refresh_token_enc="revoked-refresh-token",
        )
        preference = ContentPreference.objects.create(
            user=user,
            channel=channel,
            niche="technology",
            language="en",
            video_duration_sec=120,
            frequency="weekly",
            publish_time_local="10:00",
            publish_timezone="UTC",
        )

        def _fake_refresh(self, request):
            raise RefreshError("invalid_grant")

        with patch("channels.services.Credentials.refresh", new=_fake_refresh):
            result = services.refresh_channel_credentials(channel)

        assert result is False
        channel.refresh_from_db()
        assert channel.status == ConnectionStatus.DISCONNECTED
        assert channel.last_error_code == "invalid_grant"
        preference.refresh_from_db()
        assert preference.is_paused is True
