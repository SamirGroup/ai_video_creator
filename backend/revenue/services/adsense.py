"""AdSense Management API v2 read-only sync (FR-19, FR-20, Q2, NFR-13).

Strictly `adsense.readonly`: the data is used only to *display* an
"AdSense-confirmed" figure next to the YouTube Analytics estimate. It is never
used to move money (Risk R-1). Rows are channel-level (`job=NULL`,
`youtube_video_id=""`) because AdSense reports have no per-YouTube-video
breakdown; the YouTube host product is isolated with a `PRODUCT_NAME` filter
when the account supports it.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build as build_google_client
from googleapiclient.errors import HttpError

from channels.models import AdSenseAccount
from channels.services import GOOGLE_TOKEN_URI
from revenue.services.youtube_analytics import AnalyticsAuthError, AnalyticsRetryableError, MetricRow

logger = logging.getLogger("revenue.adsense")

ADSENSE_METRICS = ["ESTIMATED_EARNINGS", "PAGE_VIEWS", "IMPRESSIONS"]
YOUTUBE_HOST_FILTER = "PRODUCT_NAME=@YouTube"


def build_credentials_from_adsense_account(account: AdSenseAccount) -> Credentials:
    return Credentials(
        token=account.access_token_enc,
        refresh_token=account.refresh_token_enc,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=account.granted_scopes,
    )


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value)) if value not in (None, "") else Decimal("0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def parse_adsense_report(response: dict, *, filtered_to_youtube: bool) -> list[MetricRow]:
    headers = [h.get("name") for h in response.get("headers") or []]
    currency = next(
        (h.get("currencyCode") for h in response.get("headers") or [] if h.get("currencyCode")), "USD"
    )
    rows: list[MetricRow] = []
    for raw in response.get("rows") or []:
        values = [cell.get("value") for cell in raw.get("cells") or []]
        row = dict(zip(headers, values, strict=False))
        try:
            row_date = date.fromisoformat(str(row.get("DATE")))
        except (TypeError, ValueError):
            continue
        earnings = _to_decimal(row.get("ESTIMATED_EARNINGS"))
        rows.append(
            MetricRow(
                date=row_date,
                youtube_video_id="",
                views=int(float(row.get("PAGE_VIEWS") or 0)),
                estimated_revenue=earnings,
                estimated_ad_revenue=earnings,
                raw={**row, "currency": currency, "youtube_host_filter": filtered_to_youtube},
            )
        )
    return rows


def _date_params(start: date, end: date) -> dict:
    return {
        "startDate_year": start.year,
        "startDate_month": start.month,
        "startDate_day": start.day,
        "endDate_year": end.year,
        "endDate_month": end.month,
        "endDate_day": end.day,
    }


def _generate(adsense, account_name: str, start: date, end: date, *, filters: list[str] | None) -> dict:
    params = {
        "account": account_name,
        "dateRange": "CUSTOM",
        "dimensions": ["DATE"],
        "metrics": ADSENSE_METRICS,
        **_date_params(start, end),
    }
    if filters:
        params["filters"] = filters
    return adsense.accounts().reports().generate(**params).execute()


def _status(exc: HttpError) -> int:
    return int(getattr(exc.resp, "status", 0) or 0)


def fetch_adsense_daily_earnings(account: AdSenseAccount, start: date, end: date) -> list[MetricRow]:
    """`accounts.reports.generate` (read-only). Tries the YouTube host filter
    first; if the account rejects it (400) falls back to the account total and
    flags it in `raw`. 429/5xx -> AnalyticsRetryableError; 401/403 ->
    AnalyticsAuthError.
    """
    credentials = build_credentials_from_adsense_account(account)
    adsense = build_google_client("adsense", "v2", credentials=credentials, cache_discovery=False)
    account_name = account.adsense_account_id
    if not account_name.startswith("accounts/"):
        account_name = f"accounts/{account_name}"

    try:
        response = _generate(adsense, account_name, start, end, filters=[YOUTUBE_HOST_FILTER])
        filtered = True
    except HttpError as exc:
        status = _status(exc)
        if status == 429 or status >= 500:
            raise AnalyticsRetryableError(str(exc)) from exc
        if status in (401, 403):
            raise AnalyticsAuthError(str(exc)) from exc
        logger.info("adsense_youtube_filter_rejected", extra={"status": status})
        try:
            response = _generate(adsense, account_name, start, end, filters=None)
        except HttpError as exc2:
            status2 = _status(exc2)
            if status2 == 429 or status2 >= 500:
                raise AnalyticsRetryableError(str(exc2)) from exc2
            raise AnalyticsAuthError(str(exc2)) from exc2
        filtered = False
    return parse_adsense_report(response, filtered_to_youtube=filtered)
