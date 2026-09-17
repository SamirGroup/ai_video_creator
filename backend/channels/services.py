"""OAuth (Google) + YouTube Data API / AdSense Management API integration
services for the `channels` app.

Implements the real authorization-code + PKCE flow (FR-10, FR-11, NFR-4), the
channel-fetch/persist step of the callback (FR-12, FR-13, FR-16), token
refresh (FR-14) and revoke (FR-15) via `google-auth-oauthlib` /
`google-api-python-client`. There is no browser automation and no credential
handling of any kind here (C-1, C-2) — only the official OAuth 2.0
authorization-code grant and official Google APIs.

Views stay thin; every Google-facing call and every DB side-effect lives here
so it can be unit-tested by mocking this module's boundaries (see
`channels/tests/test_oauth.py`).
"""

from __future__ import annotations

import dataclasses
import logging
import secrets
from datetime import timedelta, timezone as dt_timezone

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build as build_google_client
from googleapiclient.errors import HttpError

from channels.models import (
    AdSenseAccount,
    ConnectionStatus,
    MonetizationSource,
    YouTubeChannel,
)

logger = logging.getLogger("channels.services")

# NFR-4: state token is one-time and short-lived.
OAUTH_STATE_TTL_SECONDS = 10 * 60

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]

ADSENSE_SCOPES = [
    "https://www.googleapis.com/auth/adsense.readonly",
]

GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URI = "https://oauth2.googleapis.com/revoke"


class OAuthStateError(Exception):
    """Missing/expired/reused `state`, or one that doesn't match the caller (NFR-4)."""


class OAuthExchangeError(Exception):
    """Google rejected the code/consent, or a downstream API call failed
    (invalid_grant, access_denied, redirect_uri_mismatch, quota, ...).
    """


class ChannelAlreadyLinkedError(Exception):
    """FR-16: the YouTube channel (or AdSense account) is already linked to a
    different platform account.
    """


@dataclasses.dataclass
class PendingOAuthState:
    user_id: str
    code_verifier: str
    redirect_uri: str
    scopes: list[str]


# ---------------------------------------------------------------------------
# Authorization-code + PKCE flow (FR-10, FR-11, FR-19, NFR-4)
# ---------------------------------------------------------------------------


def _cache_key(kind: str, state: str) -> str:
    return f"oauth:{kind}:state:{state}"


def _client_config(redirect_uri: str) -> dict:
    return {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
            "redirect_uris": [redirect_uri],
        }
    }


def _generate_code_verifier() -> str:
    # RFC 7636 requires 43-128 unreserved characters (S256 challenge below).
    return secrets.token_urlsafe(96)[:128]


def build_authorization_request(
    *, kind: str, user_id, scopes: list[str], redirect_uri: str
) -> tuple[str, str]:
    """Starts the authorization-code + PKCE flow.

    `kind` namespaces the cache key ("youtube" / "adsense") so the two consent
    flows (FR-10..18 vs FR-19) never collide. Returns (authorization_url, state).
    The state + PKCE code_verifier are stashed server-side (cache, 10 min TTL)
    keyed by `state` — nothing about the flow is trusted from the client at
    callback time beyond that lookup.
    """
    code_verifier = _generate_code_verifier()
    flow = Flow.from_client_config(
        _client_config(redirect_uri),
        scopes=scopes,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    state = secrets.token_urlsafe(32)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        state=state,
    )
    pending = PendingOAuthState(
        user_id=str(user_id),
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
        scopes=list(scopes),
    )
    cache.set(
        _cache_key(kind, state),
        dataclasses.asdict(pending),
        timeout=OAUTH_STATE_TTL_SECONDS,
    )
    return authorization_url, state


def consume_oauth_state(*, kind: str, state: str, user_id) -> PendingOAuthState:
    """Validates and one-time-consumes a previously issued `state` (NFR-4).

    Raises OAuthStateError if missing/expired/already used, or if it does not
    belong to the currently authenticated user (defense in depth against a
    replayed/shared callback URL).
    """
    key = _cache_key(kind, state)
    raw = cache.get(key)
    if not raw:
        raise OAuthStateError("Invalid or expired OAuth state.")
    if raw.get("user_id") != str(user_id):
        raise OAuthStateError("OAuth state does not belong to the current user.")
    if not cache.add(key + ":consumed", True, timeout=OAUTH_STATE_TTL_SECONDS):
        raise OAuthStateError("OAuth state has already been consumed.")
    cache.delete(key)
    return PendingOAuthState(**raw)


def exchange_code_for_credentials(
    *, code: str, pending: PendingOAuthState
) -> Credentials:
    """FR-12: exchanges the authorization code for tokens.

    Raises OAuthExchangeError on any Google-side rejection (invalid_grant,
    access_denied, redirect_uri_mismatch, ...).
    """
    flow = Flow.from_client_config(
        _client_config(pending.redirect_uri),
        scopes=pending.scopes,
        redirect_uri=pending.redirect_uri,
        code_verifier=pending.code_verifier,
        autogenerate_code_verifier=False,
    )
    try:
        flow.fetch_token(code=code)
    except Exception as exc:  # oauthlib raises its own exception hierarchy
        logger.warning("oauth_token_exchange_failed", extra={"error": str(exc)})
        raise OAuthExchangeError(str(exc)) from exc
    return flow.credentials


def _to_aware_utc(dt):
    """google-auth returns naive UTC datetimes; Django needs aware ones (USE_TZ=True)."""
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, dt_timezone.utc)
    return dt


def _safe_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# YouTube channel (FR-12, FR-13, FR-16, FR-17)
# ---------------------------------------------------------------------------


def fetch_own_channel(credentials: Credentials) -> dict:
    """FR-12: `channels.list(mine=true)` — the only channel-identity call made
    before persisting anything, ahead of the FR-16 uniqueness check.
    """
    youtube = build_google_client(
        "youtube", "v3", credentials=credentials, cache_discovery=False
    )
    try:
        response = (
            youtube.channels()
            .list(part="snippet,statistics,status", mine=True)
            .execute()
        )
    except HttpError as exc:
        raise OAuthExchangeError(f"YouTube channels.list failed: {exc}") from exc

    items = response.get("items") or []
    if not items:
        raise OAuthExchangeError(
            "This Google account has no accessible YouTube channel."
        )
    return items[0]


def persist_youtube_channel(
    *, user, credentials: Credentials, channel_payload: dict, granted_scopes: list[str]
) -> tuple[YouTubeChannel, bool]:
    """FR-12, FR-13, FR-16: creates/updates the `YouTubeChannel` row for `user`.

    Raises ChannelAlreadyLinkedError if the YouTube channel is already
    connected to a *different* platform account (unique constraint on
    `youtube_channel_id`, enforced here with a clear error before hitting the
    DB constraint).
    """
    youtube_channel_id = channel_payload["id"]
    snippet = channel_payload.get("snippet", {})
    statistics = channel_payload.get("statistics", {})

    existing = YouTubeChannel.objects.filter(
        youtube_channel_id=youtube_channel_id
    ).first()
    if existing is not None and existing.user_id != user.id:
        raise ChannelAlreadyLinkedError(
            "This YouTube channel is already connected to another account."
        )

    channel, created = YouTubeChannel.objects.update_or_create(
        user=user,
        youtube_channel_id=youtube_channel_id,
        defaults={
            "channel_title": snippet.get("title", ""),
            "channel_handle": snippet.get("customUrl", ""),
            "thumbnail_url": (
                (snippet.get("thumbnails") or {}).get("default") or {}
            ).get("url", ""),
            "subscriber_count": _safe_int(statistics.get("subscriberCount")),
            "video_count": _safe_int(statistics.get("videoCount")),
            # YouTube Data API v3's `channels` resource does not expose YPP /
            # monetization status for this scope set — FR-17 falls back to
            # self-declaration in the UI until/unless a dedicated signal is
            # available (Content Owner / Reporting API is out of MVP scope).
            "is_monetized": None,
            "monetization_source": MonetizationSource.UNKNOWN,
            "access_token_enc": credentials.token,
            "refresh_token_enc": credentials.refresh_token
            or (existing.refresh_token_enc if existing else None),
            "token_key_version": 1,
            "token_expires_at": _to_aware_utc(credentials.expiry),
            "granted_scopes": list(granted_scopes),
            "status": ConnectionStatus.CONNECTED,
            "last_error_code": "",
            "connected_at": timezone.now(),
            "disconnected_at": None,
        },
    )
    return channel, created


def build_credentials_from_channel(channel: YouTubeChannel) -> Credentials:
    return Credentials(
        token=channel.access_token_enc,
        refresh_token=channel.refresh_token_enc,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=channel.granted_scopes,
    )


def sync_channel_metadata(channel: YouTubeChannel) -> YouTubeChannel:
    """POST /channels/{id}/sync: refresh subscriber/video counts (best effort)."""
    if not refresh_channel_credentials(channel):
        raise OAuthExchangeError(
            "Channel token could not be refreshed; it was disconnected."
        )
    channel.refresh_from_db()
    credentials = build_credentials_from_channel(channel)
    payload = fetch_own_channel(credentials)
    snippet = payload.get("snippet", {})
    statistics = payload.get("statistics", {})
    channel.channel_title = snippet.get("title", channel.channel_title)
    channel.channel_handle = snippet.get("customUrl", channel.channel_handle)
    channel.subscriber_count = _safe_int(statistics.get("subscriberCount"))
    channel.video_count = _safe_int(statistics.get("videoCount"))
    channel.last_synced_at = timezone.now()
    channel.save(
        update_fields=[
            "channel_title",
            "channel_handle",
            "subscriber_count",
            "video_count",
            "last_synced_at",
            "updated_at",
        ]
    )
    return channel


# ---------------------------------------------------------------------------
# AdSense account (FR-19, FR-20)
# ---------------------------------------------------------------------------


def fetch_adsense_account(credentials: Credentials) -> dict:
    adsense = build_google_client(
        "adsense", "v2", credentials=credentials, cache_discovery=False
    )
    try:
        response = adsense.accounts().list().execute()
    except HttpError as exc:
        raise OAuthExchangeError(f"AdSense accounts.list failed: {exc}") from exc

    accounts = response.get("accounts") or []
    if not accounts:
        raise OAuthExchangeError(
            "This Google account has no accessible AdSense account."
        )
    return accounts[0]


def persist_adsense_account(
    *, user, credentials: Credentials, account_payload: dict, granted_scopes: list[str]
) -> tuple[AdSenseAccount, bool]:
    # AdSense resource names look like "accounts/pub-1234567890123456" — used
    # as-is as the stable external id (SPEC 5.4).
    adsense_account_id = account_payload.get("name", "")
    existing = AdSenseAccount.objects.filter(
        adsense_account_id=adsense_account_id
    ).first()
    if existing is not None and existing.user_id != user.id:
        raise ChannelAlreadyLinkedError(
            "This AdSense account is already connected to another account."
        )

    account, created = AdSenseAccount.objects.update_or_create(
        user=user,
        adsense_account_id=adsense_account_id,
        defaults={
            "access_token_enc": credentials.token,
            "refresh_token_enc": credentials.refresh_token
            or (existing.refresh_token_enc if existing else None),
            "token_key_version": 1,
            "token_expires_at": _to_aware_utc(credentials.expiry),
            "granted_scopes": list(granted_scopes),
            "status": ConnectionStatus.CONNECTED,
            "connected_at": timezone.now(),
        },
    )
    return account, created


def disconnect_adsense_account(
    account: AdSenseAccount, *, actor_type: str, actor_id, request=None
) -> None:
    from audit.services import record_audit_event

    token = account.refresh_token_enc or account.access_token_enc
    if token:
        revoke_google_token(token)

    account.access_token_enc = None
    account.refresh_token_enc = None
    account.status = ConnectionStatus.DISCONNECTED
    account.save(
        update_fields=["access_token_enc", "refresh_token_enc", "status", "updated_at"]
    )

    record_audit_event(
        actor_type=actor_type,
        actor_id=actor_id,
        action="oauth.revoked",
        resource_type="adsense_account",
        resource_id=str(account.id),
        request=request,
    )


# ---------------------------------------------------------------------------
# Revoke (FR-15) and refresh (FR-14)
# ---------------------------------------------------------------------------


def revoke_google_token(token: str) -> bool:
    """FR-15: calls Google's token revocation endpoint. Google returns 200 even
    for an already-invalid token, which we also treat as a successful revoke
    from our side (the point is our tokens are gone either way).
    """
    try:
        response = requests.post(GOOGLE_REVOKE_URI, params={"token": token}, timeout=10)
    except requests.RequestException as exc:
        logger.error("google_revoke_request_failed", extra={"error": str(exc)})
        return False
    if response.status_code not in (200, 400):
        logger.error(
            "google_revoke_unexpected_status", extra={"status": response.status_code}
        )
        return False
    return True


def _pause_scheduled_content(channel: YouTubeChannel) -> None:
    from content_planning.models import ContentPreference

    # FR-14/FR-15: "rejalashtirilgan job'lar paused" — Celery Beat's scheduler
    # (FR-35) creates new video_jobs from ContentPreference, so pausing the
    # preference is what actually stops new scheduled generation for this
    # channel; in-flight jobs are left for video_pipeline to handle on their
    # own terms (they check channel connectivity at each stage).
    ContentPreference.objects.filter(channel_id=channel.id).update(is_paused=True)


def disconnect_channel(
    channel: YouTubeChannel, *, actor_type: str, actor_id, request=None
) -> None:
    """FR-15: revoke at Google, hard-delete the stored tokens (never
    soft-delete), pause scheduled generation, and write an audit trail entry.
    """
    from audit.services import record_audit_event

    token = channel.refresh_token_enc or channel.access_token_enc
    if token:
        revoke_google_token(token)

    channel.access_token_enc = None
    channel.refresh_token_enc = None
    channel.status = ConnectionStatus.DISCONNECTED
    channel.disconnected_at = timezone.now()
    channel.save(
        update_fields=[
            "access_token_enc",
            "refresh_token_enc",
            "status",
            "disconnected_at",
            "updated_at",
        ]
    )

    _pause_scheduled_content(channel)

    record_audit_event(
        actor_type=actor_type,
        actor_id=actor_id,
        action="oauth.revoked",
        resource_type="youtube_channel",
        resource_id=str(channel.id),
        request=request,
    )


def _mark_channel_disconnected_after_refresh_failure(
    channel: YouTubeChannel, *, error_code: str
) -> None:
    """FR-14: refresh failed (invalid_grant/revoked) — move to `disconnected`,
    pause scheduling, notify the creator, and audit the transition. Tokens are
    intentionally left as-is here (unlike the explicit FR-15 disconnect path)
    since they are already unusable and this is a system-detected condition,
    not a user action.
    """
    from audit.services import record_audit_event
    from notifications.models import Notification, NotificationChannel

    channel.status = ConnectionStatus.DISCONNECTED
    channel.last_error_code = error_code
    channel.disconnected_at = timezone.now()
    channel.save(
        update_fields=["status", "last_error_code", "disconnected_at", "updated_at"]
    )

    _pause_scheduled_content(channel)

    Notification.objects.create(
        user_id=channel.user_id,
        type="channel_disconnected",
        channel=NotificationChannel.EMAIL,
        title="Your YouTube channel was disconnected",
        body=(
            f'We could not refresh access to "{channel.channel_title or channel.youtube_channel_id}". '
            "Please reconnect it from your dashboard to resume video generation."
        ),
        payload={"channel_id": str(channel.id), "error_code": error_code},
    )

    record_audit_event(
        actor_type="system",
        action="channel.disconnected",
        resource_type="youtube_channel",
        resource_id=str(channel.id),
        metadata={"error_code": error_code},
    )


def refresh_channel_credentials(channel: YouTubeChannel) -> bool:
    """FR-14: refreshes the stored access token via the refresh token.

    Returns True if the channel remains usable, False if it was moved to
    `disconnected` (invalid_grant/revoked). Safe to call unconditionally
    (e.g. from a Celery Beat task, see `channels/tasks.py`) — a channel with
    a still-valid token is simply refreshed again a little early.
    """
    if channel.status != ConnectionStatus.CONNECTED or not channel.refresh_token_enc:
        return channel.status == ConnectionStatus.CONNECTED

    credentials = build_credentials_from_channel(channel)
    try:
        credentials.refresh(GoogleAuthRequest())
    except RefreshError as exc:
        logger.warning(
            "oauth_refresh_failed",
            extra={"channel_id": str(channel.id), "error": str(exc)},
        )
        _mark_channel_disconnected_after_refresh_failure(
            channel, error_code="invalid_grant"
        )
        return False

    channel.access_token_enc = credentials.token
    if credentials.refresh_token:
        channel.refresh_token_enc = credentials.refresh_token
    channel.token_expires_at = _to_aware_utc(credentials.expiry)
    channel.save(
        update_fields=[
            "access_token_enc",
            "refresh_token_enc",
            "token_expires_at",
            "updated_at",
        ]
    )
    return True


# Exposed for channels/tasks.py's Celery Beat lookahead query.
TOKEN_REFRESH_LOOKAHEAD = timedelta(minutes=30)
