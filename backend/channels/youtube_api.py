"""YouTube Data API v3 client factory + error classification (Track C).

Every YouTube call in the platform goes through `youtube_client_for_channel`
so that (a) the access token is refreshed *before* it expires (FR-14) and
(b) only the official `google-api-python-client` is ever used (C-2). There is
no browser automation anywhere in this codebase.

`classify_http_error` turns a `googleapiclient.errors.HttpError` into one of
six operational buckets so the upload stage (FR-57) and the post-publish
checks (FR-59/FR-60) can react differently to quota exhaustion, revoked
access, and transient backend errors.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Literal

from django.utils import timezone
from googleapiclient.discovery import build as build_google_client
from googleapiclient.errors import HttpError

from channels.models import ConnectionStatus, YouTubeChannel
from channels.services import build_credentials_from_channel, refresh_channel_credentials

logger = logging.getLogger("channels.youtube_api")

ErrorKind = Literal["quota_exceeded", "forbidden", "invalid_grant", "not_found", "retryable", "fatal"]

# Refresh when the token expires within this window: a resumable upload of a
# large file can easily run for several minutes.
TOKEN_EXPIRY_LOOKAHEAD = timedelta(minutes=10)

# reason -> bucket. See https://developers.google.com/youtube/v3/docs/errors
_QUOTA_REASONS = {
    "quotaExceeded",
    "dailyLimitExceeded",
    "dailyLimitExceededUnreg",
    "uploadLimitExceeded",  # channel-level daily upload cap; also clears at the next window
}
_FORBIDDEN_REASONS = {
    "forbidden",
    "insufficientPermissions",
    "insufficientScopes",
    "accessNotConfigured",
    "youtubeSignupRequired",
    "channelSuspended",
    "channelClosed",
    "accountDeleted",
    "accountSuspended",
    "accountTerminated",
}
_AUTH_REASONS = {"authError", "invalidCredentials", "invalid_grant", "unauthorized", "UNAUTHENTICATED"}
_RETRYABLE_REASONS = {
    "backendError",
    "internalError",
    "rateLimitExceeded",
    "userRateLimitExceeded",
    "servingLimitExceeded",
    "processingFailure",
}


class ChannelNotConnected(Exception):
    """The channel has no usable credentials (disconnected/revoked, or the
    refresh just failed and `refresh_channel_credentials` moved it to
    `disconnected`). Callers treat this exactly like `invalid_grant`.
    """

    def __init__(self, channel: YouTubeChannel, message: str = ""):
        super().__init__(message or f"Channel {channel.id} is not connected.")
        self.channel = channel


def youtube_client_for_channel(channel: YouTubeChannel, *, refresh: bool = True):
    """Build an authenticated `youtube` v3 service for `channel`.

    Refreshes the access token first when it is missing, expired, or expiring
    within `TOKEN_EXPIRY_LOOKAHEAD`. Raises `ChannelNotConnected` when the
    channel is not `connected` or the refresh failed (the channel is then
    already `disconnected`, the creator notified and scheduling paused —
    `channels.services._mark_channel_disconnected_after_refresh_failure`).
    """
    if channel.status != ConnectionStatus.CONNECTED or not channel.access_token_enc:
        raise ChannelNotConnected(channel)

    if refresh and _token_needs_refresh(channel):
        if not refresh_channel_credentials(channel):
            raise ChannelNotConnected(channel, "Token refresh failed; channel disconnected.")
        channel.refresh_from_db(fields=["access_token_enc", "refresh_token_enc", "token_expires_at", "status"])

    credentials = build_credentials_from_channel(channel)
    return build_google_client("youtube", "v3", credentials=credentials, cache_discovery=False)


def _token_needs_refresh(channel: YouTubeChannel) -> bool:
    if not channel.refresh_token_enc:
        return False
    if channel.token_expires_at is None:
        return True
    return channel.token_expires_at <= timezone.now() + TOKEN_EXPIRY_LOOKAHEAD


def http_error_reasons(exc: HttpError) -> list[str]:
    """`error.errors[].reason` values (plus the top-level `error.status`) from
    the JSON body Google attaches to an HttpError. Never raises.
    """
    reasons: list[str] = []
    content = getattr(exc, "content", b"") or b""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    try:
        payload = json.loads(content) if content else {}
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        for item in error.get("errors") or []:
            if isinstance(item, dict) and item.get("reason"):
                reasons.append(str(item["reason"]))
        if error.get("status"):
            reasons.append(str(error["status"]))
        for detail in error.get("details") or []:
            if isinstance(detail, dict) and detail.get("reason"):
                reasons.append(str(detail["reason"]))
    return reasons


def classify_http_error(exc: HttpError) -> ErrorKind:
    """Map an HttpError onto the FR-57 handling buckets.

    quota_exceeded  -> re-queue at the next Pacific-midnight window (job not failed)
    forbidden       -> channel access revoked/insufficient -> channel `disconnected`
    invalid_grant   -> token unusable -> channel `disconnected`
    not_found       -> the video no longer exists (post-publish: deleted_on_youtube)
    retryable       -> 5xx / rate limit -> FR-44 backoff ladder
    fatal           -> deterministic 4xx (bad metadata, invalid file) -> `failed`
    """
    status = int(getattr(getattr(exc, "resp", None), "status", 0) or 0)
    reasons = set(http_error_reasons(exc))

    if reasons & _QUOTA_REASONS:
        return "quota_exceeded"
    if status == 401 or reasons & _AUTH_REASONS:
        return "invalid_grant"
    if reasons & _RETRYABLE_REASONS:
        # rateLimitExceeded/userRateLimitExceeded arrive as 403 but are transient.
        return "retryable"
    if status == 403:
        return "forbidden"
    if status == 404 or "NOT_FOUND" in reasons:
        return "not_found"
    if status == 429 or status >= 500:
        return "retryable"
    return "fatal"
