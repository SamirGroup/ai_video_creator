"""Idempotent persistence of daily metrics (FR-62, FR-63, AC-7).

`upsert_records` writes through `bulk_create(update_conflicts=True)` keyed on
the SPEC 5.16 unique constraint `(source, channel, youtube_video_id, date)`,
so running a sync twice never duplicates a row. Rows whose date is older than
`FINAL_AFTER_HOURS` are flagged `is_final=True` (YouTube revises data for
48-72h); only final rows enter a statement (FR-67).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from channels.models import AdSenseAccount, ConnectionStatus, YouTubeChannel
from channels.services import refresh_channel_credentials
from revenue.models import RevenueRecord, RevenueSource
from revenue.services.adsense import fetch_adsense_daily_earnings
from revenue.services.youtube_analytics import MetricRow, fetch_channel_daily_metrics

logger = logging.getLogger("revenue.sync")

SYNC_WINDOW_DAYS = 35  # FR-63
FINAL_AFTER_HOURS = 72  # FR-63
_FOUR_DP = Decimal("0.0001")

_UPDATE_FIELDS = [
    "user",
    "job",
    "views",
    "estimated_minutes_watched",
    "estimated_revenue",
    "estimated_ad_revenue",
    "cpm",
    "rpm",
    "currency",
    "is_final",
    "synced_at",
    "raw_payload",
]


def final_cutoff_date(now=None) -> date:
    """Rows dated on/before this date are considered final (72h rule)."""
    now = now or timezone.now()
    return (now - timedelta(hours=FINAL_AFTER_HOURS)).date()


def _job_map(channel: YouTubeChannel, video_ids: set[str]) -> dict[str, object]:
    from video_pipeline.models import VideoJob

    if not video_ids:
        return {}
    return {
        vid: job_id
        for job_id, vid in VideoJob.objects.filter(channel=channel, youtube_video_id__in=video_ids)
        .exclude(youtube_video_id="")
        .values_list("id", "youtube_video_id")
    }


def _rpm(row: MetricRow):
    if row.views <= 0 or row.estimated_revenue == 0:
        return None
    return (row.estimated_revenue / row.views * 1000).quantize(_FOUR_DP)


def upsert_records(
    *, channel: YouTubeChannel, source: str, rows: list[MetricRow], synced_at=None, currency: str = "USD"
) -> int:
    """Idempotent upsert on `(source, channel, youtube_video_id, date)`.
    Returns the number of rows written. Maps `youtube_video_id` -> `job` FK.
    """
    if not rows:
        return 0
    synced_at = synced_at or timezone.now()
    cutoff = final_cutoff_date(synced_at)
    jobs = _job_map(channel, {r.youtube_video_id for r in rows if r.youtube_video_id})

    # Collapse duplicates inside one batch so ON CONFLICT never sees the same key twice.
    by_key: dict[tuple, RevenueRecord] = {}
    for row in rows:
        payload = dict(row.raw)
        if row.revenue_unavailable_reason:
            payload["revenue_unavailable_reason"] = row.revenue_unavailable_reason
        if row.playback_based_cpm is not None:
            payload["playbackBasedCpm"] = str(row.playback_based_cpm)
        by_key[(row.youtube_video_id, row.date)] = RevenueRecord(
            user_id=channel.user_id,
            channel=channel,
            job_id=jobs.get(row.youtube_video_id),
            youtube_video_id=row.youtube_video_id,
            source=source,
            date=row.date,
            views=row.views,
            estimated_minutes_watched=row.estimated_minutes_watched,
            estimated_revenue=row.estimated_revenue,
            estimated_ad_revenue=row.estimated_ad_revenue,
            cpm=row.cpm,
            rpm=_rpm(row),
            currency=str(payload.get("currency") or currency)[:3].upper(),
            is_final=row.date <= cutoff,
            synced_at=synced_at,
            raw_payload=payload,
        )

    objs = list(by_key.values())
    with transaction.atomic():
        RevenueRecord.objects.bulk_create(
            objs,
            update_conflicts=True,
            unique_fields=["source", "channel", "youtube_video_id", "date"],
            update_fields=_UPDATE_FIELDS,
            batch_size=500,
        )
    return len(objs)


def mark_final_rows(channel: YouTubeChannel, now=None) -> int:
    """FR-63: flips `is_final` on rows older than 72h that were never re-synced."""
    return RevenueRecord.objects.filter(
        channel=channel, is_final=False, date__lte=final_cutoff_date(now)
    ).update(is_final=True)


def sync_window(now=None, days: int = SYNC_WINDOW_DAYS) -> tuple[date, date]:
    today = (now or timezone.now()).date()
    return today - timedelta(days=days), today


def sync_channel(channel: YouTubeChannel, *, days: int = SYNC_WINDOW_DAYS, now=None) -> dict:
    """Full FR-61..FR-63 sync for one channel. Returns a small stats dict.
    Raises AnalyticsRetryableError (task retries) / AnalyticsAuthError.
    A channel whose refresh fails is disconnected by `channels.services` and
    skipped here (`{"skipped": "disconnected"}`).
    """
    if channel.status != ConnectionStatus.CONNECTED:
        return {"skipped": "not_connected"}
    if not refresh_channel_credentials(channel):
        return {"skipped": "disconnected"}
    channel.refresh_from_db()

    start, end = sync_window(now, days)
    metrics = fetch_channel_daily_metrics(channel, start, end)
    synced_at = now or timezone.now()
    written = upsert_records(
        channel=channel,
        source=RevenueSource.YOUTUBE_ANALYTICS,
        rows=metrics.channel_rows + metrics.video_rows,
        synced_at=synced_at,
    )
    finalized = mark_final_rows(channel, synced_at)
    channel.last_synced_at = synced_at
    channel.save(update_fields=["last_synced_at", "updated_at"])
    logger.info(
        "revenue_channel_synced",
        extra={"channel_id": str(channel.id), "rows": written, "reason": metrics.revenue_unavailable_reason},
    )
    return {
        "rows": written,
        "finalized": finalized,
        "revenue_unavailable_reason": metrics.revenue_unavailable_reason,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def sync_adsense_account(account: AdSenseAccount, *, days: int = SYNC_WINDOW_DAYS, now=None) -> dict:
    """FR-19/FR-20: AdSense channel-level rows for the user's connected channel."""
    if account.status != ConnectionStatus.CONNECTED:
        return {"skipped": "not_connected"}
    channel = (
        YouTubeChannel.objects.filter(user_id=account.user_id, status=ConnectionStatus.CONNECTED)
        .order_by("connected_at")
        .first()
    )
    if channel is None:
        return {"skipped": "no_channel"}

    start, end = sync_window(now, days)
    rows = fetch_adsense_daily_earnings(account, start, end)
    synced_at = now or timezone.now()
    written = upsert_records(channel=channel, source=RevenueSource.ADSENSE, rows=rows, synced_at=synced_at)
    mark_final_rows(channel, synced_at)
    account.last_synced_at = synced_at
    account.save(update_fields=["last_synced_at", "updated_at"])
    return {"rows": written, "start": start.isoformat(), "end": end.isoformat()}
