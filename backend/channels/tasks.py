"""Celery tasks for OAuth token lifecycle management (FR-14).

Wiring the actual periodic schedule (Celery Beat, e.g. "every 15 minutes") is
an admin/ops configuration step via django-celery-beat, not code — consistent
with the rest of the platform's "config over hardcoding" convention
(`api_credentials_config`, `plans`, ...). This module only provides the task
itself.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from channels.models import ConnectionStatus, YouTubeChannel
from channels.services import TOKEN_REFRESH_LOOKAHEAD, refresh_channel_credentials

logger = logging.getLogger("channels.tasks")


@shared_task(name="channels.refresh_expiring_channel_tokens")
def refresh_expiring_channel_tokens() -> int:
    """FR-14: refreshes every connected channel's access token that is expired
    or about to expire within `TOKEN_REFRESH_LOOKAHEAD`. Returns the number of
    channels processed. Idempotent — re-running early just refreshes again.
    """
    threshold = timezone.now() + TOKEN_REFRESH_LOOKAHEAD
    channels = YouTubeChannel.objects.filter(
        status=ConnectionStatus.CONNECTED,
        token_expires_at__lte=threshold,
        refresh_token_enc__isnull=False,
    )
    processed = 0
    for channel in channels:
        try:
            refresh_channel_credentials(channel)
        except Exception:  # noqa: BLE001 — one bad channel must not stop the batch
            logger.exception("channel_token_refresh_task_failed", extra={"channel_id": str(channel.id)})
        processed += 1
    return processed


@shared_task(name="channels.refresh_single_channel_token")
def refresh_single_channel_token(channel_id: str) -> bool:
    """On-demand refresh for a single channel — e.g. called defensively right
    before a video_pipeline stage that needs a valid access token.
    """
    try:
        channel = YouTubeChannel.objects.get(id=channel_id)
    except YouTubeChannel.DoesNotExist:
        return False
    return refresh_channel_credentials(channel)
