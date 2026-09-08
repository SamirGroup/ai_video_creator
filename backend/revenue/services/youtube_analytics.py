"""YouTube Analytics API v2 client for FR-61..FR-63, FR-66.

Only the official `youtubeAnalytics` discovery client is used (C-2). Two
report shapes are fetched per channel:

* channel level  — `dimensions=day`  (one row per day, all videos);
* video level    — `dimensions=day,video` filtered to the platform's own
  `youtube_video_id`s in batches whose `filters` string stays <= 500 chars
  (API limit), so "platform-generated vs other" (FR-64/FR-65) is exact.

Monetary metrics (`estimatedRevenue`, `estimatedAdRevenue`, `cpm`,
`playbackBasedCpm`) require the `yt-analytics-monetary.readonly` scope and a
monetized channel. When they are unavailable the query is retried without
them and every resulting row carries `revenue_unavailable_reason` so the
dashboard can explain a zero instead of inventing a number (FR-66, AC-7).
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from googleapiclient.discovery import build as build_google_client
from googleapiclient.errors import HttpError

from channels.models import YouTubeChannel
from channels.services import build_credentials_from_channel

logger = logging.getLogger("revenue.youtube_analytics")

MONETARY_SCOPE = "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"

BASE_METRICS = ["views", "estimatedMinutesWatched"]
MONETARY_METRICS = ["estimatedRevenue", "estimatedAdRevenue", "cpm", "playbackBasedCpm"]

# `filters=video==a,b,c` must stay under 500 characters (API constraint).
MAX_FILTER_CHARS = 500
PAGE_SIZE = 500

REASON_SCOPE_NOT_GRANTED = "monetary_scope_not_granted"
REASON_SCOPE_DENIED = "monetary_scope_denied"
REASON_NOT_MONETIZED = "channel_not_monetized"


class AnalyticsRetryableError(Exception):
    """429 / 5xx from the Analytics API — the Celery task retries with backoff."""


class AnalyticsAuthError(Exception):
    """401/403 that is not about monetary metrics (revoked token etc.)."""


@dataclasses.dataclass
class MetricRow:
    date: date
    youtube_video_id: str  # "" for channel-level rows
    views: int = 0
    estimated_minutes_watched: int = 0
    estimated_revenue: Decimal = Decimal("0")
    estimated_ad_revenue: Decimal = Decimal("0")
    cpm: Decimal | None = None
    playback_based_cpm: Decimal | None = None
    revenue_unavailable_reason: str | None = None
    raw: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ChannelMetrics:
    channel_rows: list[MetricRow]
    video_rows: list[MetricRow]
    revenue_unavailable_reason: str | None


def _to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _to_int(value) -> int:
    try:
        return int(float(value)) if value not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


def parse_report(response: dict, *, revenue_unavailable_reason: str | None = None) -> list[MetricRow]:
    """Turns an Analytics `reports.query` response into `MetricRow`s.

    Missing monetary columns (scope denied / retried without them) yield
    revenue 0 with the reason attached — never a guessed value (FR-66).
    """
    headers = [h.get("name") for h in response.get("columnHeaders") or []]
    rows_out: list[MetricRow] = []
    has_monetary = "estimatedRevenue" in headers
    reason = revenue_unavailable_reason
    if not has_monetary and reason is None:
        reason = REASON_SCOPE_DENIED

    for raw_row in response.get("rows") or []:
        row = dict(zip(headers, raw_row, strict=False))
        day = row.get("day")
        if not day:
            continue
        try:
            row_date = date.fromisoformat(str(day))
        except ValueError:
            continue
        rows_out.append(
            MetricRow(
                date=row_date,
                youtube_video_id=str(row.get("video") or ""),
                views=_to_int(row.get("views")),
                estimated_minutes_watched=_to_int(row.get("estimatedMinutesWatched")),
                estimated_revenue=_to_decimal(row.get("estimatedRevenue")) if has_monetary else Decimal("0"),
                estimated_ad_revenue=(
                    _to_decimal(row.get("estimatedAdRevenue")) if "estimatedAdRevenue" in headers else Decimal("0")
                ),
                cpm=_to_decimal(row.get("cpm")) if "cpm" in headers and row.get("cpm") is not None else None,
                playback_based_cpm=(
                    _to_decimal(row.get("playbackBasedCpm"))
                    if "playbackBasedCpm" in headers and row.get("playbackBasedCpm") is not None
                    else None
                ),
                revenue_unavailable_reason=reason,
                raw=row,
            )
        )
    return rows_out


def batch_video_ids(video_ids: list[str], *, max_chars: int = MAX_FILTER_CHARS) -> list[list[str]]:
    """Splits ids so that `"video==" + ",".join(batch)` stays <= `max_chars`."""
    batches: list[list[str]] = []
    current: list[str] = []
    current_len = len("video==")
    for vid in video_ids:
        extra = len(vid) + (1 if current else 0)
        if current and current_len + extra > max_chars:
            batches.append(current)
            current, current_len = [], len("video==")
            extra = len(vid)
        current.append(vid)
        current_len += extra
    if current:
        batches.append(current)
    return batches


def _http_status(exc: HttpError) -> int:
    try:
        return int(exc.resp.status)
    except (AttributeError, TypeError, ValueError):
        return 0


def _is_monetary_rejection(exc: HttpError) -> bool:
    status = _http_status(exc)
    text = str(exc).lower()
    if status == 403:
        return True
    return status == 400 and ("estimatedrevenue" in text or "monetary" in text or "metric" in text)


def _query_all_pages(analytics, **params) -> dict:
    """Follows `startIndex` paging and returns one merged response dict."""
    merged: dict = {}
    start_index = 1
    while True:
        response = analytics.reports().query(**params, maxResults=PAGE_SIZE, startIndex=start_index).execute()
        if not merged:
            merged = {"columnHeaders": response.get("columnHeaders") or [], "rows": []}
        rows = response.get("rows") or []
        merged["rows"].extend(rows)
        if len(rows) < PAGE_SIZE:
            return merged
        start_index += len(rows)


def _run_query(analytics, *, metrics: list[str], start: date, end: date, dimensions: str, filters: str | None) -> dict:
    params = {
        "ids": "channel==MINE",
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "metrics": ",".join(metrics),
        "dimensions": dimensions,
        "sort": "day",
    }
    if filters:
        params["filters"] = filters
    return _query_all_pages(analytics, **params)


def _query_with_monetary_fallback(
    analytics, *, want_monetary: bool, start: date, end: date, dimensions: str, filters: str | None
) -> tuple[dict, str | None]:
    """Runs the query with monetary metrics; on a monetary rejection retries
    without them and reports the reason. 429/5xx -> AnalyticsRetryableError.
    """
    metrics = BASE_METRICS + (MONETARY_METRICS if want_monetary else [])
    reason = None if want_monetary else REASON_SCOPE_NOT_GRANTED
    try:
        response = _run_query(
            analytics, metrics=metrics, start=start, end=end, dimensions=dimensions, filters=filters
        )
        return response, reason
    except HttpError as exc:
        status = _http_status(exc)
        if status == 429 or status >= 500:
            raise AnalyticsRetryableError(str(exc)) from exc
        if want_monetary and _is_monetary_rejection(exc):
            logger.info("youtube_analytics_monetary_metrics_unavailable", extra={"status": status})
            try:
                response = _run_query(
                    analytics, metrics=BASE_METRICS, start=start, end=end, dimensions=dimensions, filters=filters
                )
            except HttpError as exc2:
                status2 = _http_status(exc2)
                if status2 == 429 or status2 >= 500:
                    raise AnalyticsRetryableError(str(exc2)) from exc2
                raise AnalyticsAuthError(str(exc2)) from exc2
            return response, REASON_SCOPE_DENIED
        if status in (401, 403):
            raise AnalyticsAuthError(str(exc)) from exc
        raise


def fetch_channel_daily_metrics(
    channel: YouTubeChannel, start: date, end: date, *, video_ids: list[str] | None = None
) -> ChannelMetrics:
    """FR-61: channel-level (`day`) and video-level (`day,video`, restricted to
    `video_ids`) metrics for `[start, end]`. `video_ids` defaults to the
    platform's published videos on this channel.
    """
    if video_ids is None:
        from video_pipeline.models import VideoJob

        video_ids = list(
            VideoJob.objects.filter(channel=channel, is_platform_generated=True)
            .exclude(youtube_video_id="")
            .values_list("youtube_video_id", flat=True)
            .distinct()
        )

    credentials = build_credentials_from_channel(channel)
    analytics = build_google_client("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)

    want_monetary = MONETARY_SCOPE in (channel.granted_scopes or [])
    channel_response, reason = _query_with_monetary_fallback(
        analytics, want_monetary=want_monetary, start=start, end=end, dimensions="day", filters=None
    )
    if reason is None and channel.is_monetized is False:
        reason = REASON_NOT_MONETIZED
    channel_rows = parse_report(channel_response, revenue_unavailable_reason=reason)

    video_rows: list[MetricRow] = []
    for batch in batch_video_ids(sorted(set(video_ids))):
        response, batch_reason = _query_with_monetary_fallback(
            analytics,
            want_monetary=want_monetary and reason != REASON_SCOPE_DENIED,
            start=start,
            end=end,
            dimensions="day,video",
            filters="video==" + ",".join(batch),
        )
        video_rows.extend(parse_report(response, revenue_unavailable_reason=batch_reason or reason))

    return ChannelMetrics(channel_rows=channel_rows, video_rows=video_rows, revenue_unavailable_reason=reason)
