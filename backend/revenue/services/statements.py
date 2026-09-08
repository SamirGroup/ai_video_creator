"""Revenue-share period close (FR-67..FR-70b, A-9, A-10, AC-7).

`close_period_for_user` is idempotent (one statement per `(user, period_start,
period_end)`, the DB unique constraint backs this up) and never crashes the
batch job in `revenue.tasks.close_revenue_period` — every per-user failure is
caught, logged and audited there instead.

Rounding (FR-67 "yaxlitlash: cent darajasida, ROUND_HALF_UP, ayirma platforma
zarariga" — cent-precision, half-up, any remainder goes against the platform):
the creator's share is computed directly with `ROUND_HALF_UP`; the platform's
share is the exact remainder (`gross - creator_share`), so
`platform_share_amount + creator_share_amount == gross_revenue` holds by
construction, and a tie always rounds in the creator's favour.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from audit.services import record_audit_event
from notifications.services import notify, notify_admins
from revenue.models import RevenueRecord, RevenueShareStatement, StatementStatus
from revenue.pdf import render_statement_pdf

logger = logging.getLogger("revenue.statements")

CENT = Decimal("0.01")
DISPUTE_WINDOW = timedelta(days=14)


class StatementNotDisputable(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "STATEMENT_NOT_DISPUTABLE"
    default_detail = "This statement cannot be disputed in its current state."


class DisputeWindowClosed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "DISPUTE_WINDOW_CLOSED"
    default_detail = "The 14-day dispute window for this statement has closed."


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------
def previous_calendar_month(today: date | None = None) -> tuple[date, date]:
    """A-9: statements close for the *previous* calendar month. Half-open
    `[start, end)` — `end` is the first day of the current month.
    """
    today = today or timezone.now().date()
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month - timedelta(days=1)
    return last_month_end.replace(day=1), first_of_this_month


# ---------------------------------------------------------------------------
# Gross revenue (FR-65: platform-generated videos only)
# ---------------------------------------------------------------------------
def _revenue_rows_for_period(user, period_start: date, period_end: date) -> list[RevenueRecord]:
    """One row per `(job, date)`: AdSense (FR-20 "AdSense-confirmed") wins over
    YouTube Analytics when both are present for the same video/day.
    """
    from revenue.models import RevenueSource

    qs = (
        RevenueRecord.objects.filter(
            user=user,
            is_final=True,
            job__isnull=False,
            job__is_platform_generated=True,
            date__gte=period_start,
            date__lt=period_end,
        )
        .select_related("job")
        .order_by("job_id", "date")
    )
    by_key: dict[tuple, RevenueRecord] = {}
    for row in qs:
        key = (row.job_id, row.date)
        existing = by_key.get(key)
        if existing is None or (row.source == RevenueSource.ADSENSE and existing.source != RevenueSource.ADSENSE):
            by_key[key] = row
    return list(by_key.values())


def gross_for_period(user, period_start: date, period_end: date) -> tuple[Decimal, dict, int]:
    """`(gross_revenue, breakdown[str(job_id)] -> str(amount), video_count)`,
    all cent-quantized (FR-68 breakdown, AC-7 sum invariant).
    """
    rows = _revenue_rows_for_period(user, period_start, period_end)
    breakdown: dict[str, Decimal] = {}
    for row in rows:
        key = str(row.job_id)
        breakdown[key] = breakdown.get(key, Decimal("0")) + row.estimated_revenue
    gross = sum(breakdown.values(), Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)
    breakdown_out = {k: str(v.quantize(CENT, rounding=ROUND_HALF_UP)) for k, v in breakdown.items()}
    return gross, breakdown_out, len(breakdown)


def split_50_50(gross: Decimal, *, platform_pct: Decimal, creator_pct: Decimal) -> tuple[Decimal, Decimal]:
    """FR-67: returns `(platform_share, creator_share)`; `platform_share +
    creator_share == gross` always (platform absorbs the rounding remainder).
    """
    creator_share = (gross * creator_pct / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    platform_share = gross - creator_share
    return platform_share, creator_share


# ---------------------------------------------------------------------------
# Period close (FR-67..FR-70b)
# ---------------------------------------------------------------------------
def close_period_for_user(user, period_start: date, period_end: date) -> RevenueShareStatement | None:
    """Idempotent: a second call for the same `(user, period)` returns the
    existing statement untouched. Returns `None` when there is nothing to
    report (no platform-generated revenue, or no active contract — the latter
    is logged as an anomaly since FR-32 should prevent generation without one).
    """
    from contracts.models import Contract, ContractStatus

    existing = RevenueShareStatement.objects.filter(
        user=user, period_start=period_start, period_end=period_end
    ).first()
    if existing is not None:
        return existing

    gross, breakdown, video_count = gross_for_period(user, period_start, period_end)
    if gross <= 0:
        return None

    contract = Contract.objects.filter(user=user, status=ContractStatus.ACTIVE).order_by("-signed_at").first()
    if contract is None:
        logger.error("revenue_period_close_no_active_contract", extra={"user_id": str(user.id)})
        return None

    platform_pct = contract.contract_version.revenue_share_platform_pct
    creator_pct = contract.contract_version.revenue_share_creator_pct
    platform_share, creator_share = split_50_50(gross, platform_pct=platform_pct, creator_pct=creator_pct)

    statement = RevenueShareStatement.objects.create(
        user=user,
        period_start=period_start,
        period_end=period_end,
        currency="USD",
        gross_revenue=gross,
        platform_share_pct=platform_pct,
        platform_share_amount=platform_share,
        creator_share_amount=creator_share,
        video_count=video_count,
        breakdown=breakdown,
        contract=contract,
        status=StatementStatus.FINALIZED,
        finalized_at=timezone.now(),
    )
    record_audit_event(
        actor_type="system",
        action="revenue_share_statement.finalized",
        resource_type="revenue_share_statement",
        resource_id=str(statement.id),
        after={
            "gross_revenue": str(gross),
            "platform_share_amount": str(platform_share),
            "creator_share_amount": str(creator_share),
            "video_count": video_count,
        },
    )
    notify(
        user,
        "revenue.statement_ready",
        ctx={
            "period": f"{period_start.isoformat()} – {period_end.isoformat()}",
            "gross": str(gross),
            "currency": "USD",
            "creator_share": str(creator_share),
        },
    )
    _invoice_or_carry_forward(statement)
    return statement


def _invoice_or_carry_forward(statement: RevenueShareStatement) -> None:
    """FR-70/A-10: invoice via `billing.services.create_revenue_share_invoice`;
    below the $10 minimum -> `carried_forward` (picked up again once a later
    period's gross pushes the *cumulative* amount past the threshold — see
    `carried_forward_from` linkage in `revenue.tasks.close_revenue_period`).
    """
    from billing.services import RevenueShareInvoiceError, create_revenue_share_invoice

    try:
        invoice = create_revenue_share_invoice(statement.user, statement)
    except RevenueShareInvoiceError as exc:
        if "minimum invoiceable threshold" in str(exc):
            statement.status = StatementStatus.CARRIED_FORWARD
            statement.save(update_fields=["status", "updated_at"])
            logger.info(
                "revenue_statement_carried_forward",
                extra={"statement_id": str(statement.id), "amount": str(statement.platform_share_amount)},
            )
            return
        # FR-70a's mandatory saved payment method should make this unreachable —
        # an operational anomaly worth an admin alert, not a silent skip.
        logger.error(
            "revenue_statement_invoice_failed",
            extra={"statement_id": str(statement.id), "user_id": str(statement.user_id), "error": str(exc)},
        )
        notify_admins(
            "admin.alert",
            ctx={
                "subject": "Revenue-share invoice failed",
                "message": f"Statement {statement.id} (user {statement.user_id}): {exc}",
            },
        )
        return

    statement.status = StatementStatus.INVOICED
    statement.save(update_fields=["status", "updated_at"])
    notify(
        statement.user,
        "revenue.invoice_issued",
        ctx={
            "amount": str(invoice.amount),
            "currency": invoice.currency,
            "period": f"{statement.period_start.isoformat()} – {statement.period_end.isoformat()}",
        },
    )


# ---------------------------------------------------------------------------
# Finalize (admin, FR-67) — statements created in `draft` by an out-of-band path
# ---------------------------------------------------------------------------
def finalize_statement(staff_user, statement: RevenueShareStatement, request=None) -> RevenueShareStatement:
    if statement.status != StatementStatus.DRAFT:
        raise StatementNotDisputable(f"Statement is {statement.status}, not draft.")
    statement.status = StatementStatus.FINALIZED
    statement.finalized_at = timezone.now()
    statement.save(update_fields=["status", "finalized_at", "updated_at"])
    record_audit_event(
        actor_type="staff",
        actor_id=staff_user.id,
        action="revenue_share_statement.finalized",
        resource_type="revenue_share_statement",
        resource_id=str(statement.id),
        request=request,
        after={"status": statement.status},
    )
    _invoice_or_carry_forward(statement)
    return statement


# ---------------------------------------------------------------------------
# Dispute (FR-69)
# ---------------------------------------------------------------------------
def dispute_statement(user, statement: RevenueShareStatement, reason: str, request=None) -> RevenueShareStatement:
    if statement.status not in (StatementStatus.FINALIZED, StatementStatus.INVOICED, StatementStatus.PAID):
        raise StatementNotDisputable(f"Statement is {statement.status} and cannot be disputed.")
    if statement.finalized_at is None or timezone.now() - statement.finalized_at > DISPUTE_WINDOW:
        raise DisputeWindowClosed("The 14-day dispute window for this statement has closed.")

    statement.status = StatementStatus.DISPUTED
    statement.disputed_at = timezone.now()
    statement.dispute_reason = reason
    statement.save(update_fields=["status", "disputed_at", "dispute_reason", "updated_at"])
    record_audit_event(
        actor_type="user",
        actor_id=user.id,
        action="revenue_share_statement.disputed",
        resource_type="revenue_share_statement",
        resource_id=str(statement.id),
        request=request,
        after={"reason": reason},
    )
    notify_admins(
        "admin.alert",
        ctx={
            "subject": "Revenue-share statement disputed",
            "message": f"Statement {statement.id} (user {user.id}) disputed: {reason}",
        },
    )
    return statement


# ---------------------------------------------------------------------------
# PDF (FR-69)
# ---------------------------------------------------------------------------
def statement_pdf_bytes(statement: RevenueShareStatement) -> bytes:
    return render_statement_pdf(statement)
