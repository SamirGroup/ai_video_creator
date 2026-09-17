"""Celery tasks for the `revenue` app: FR-61..FR-63 daily sync is implemented
in `revenue.services.sync` (owned by a prior track); this module adds the
FR-67 monthly period-close job.
"""

from __future__ import annotations

import logging
from datetime import date

from celery import shared_task

logger = logging.getLogger("revenue.tasks")


@shared_task(name="revenue.close_revenue_period")
def close_revenue_period(
    period_start: str | None = None, period_end: str | None = None
) -> dict:
    """FR-67, A-9: closes the previous calendar month by default (called on the
    10th so the 35-day/72h revision window in FR-63 has mostly settled).
    Idempotent per user+period; one bad user never aborts the batch.
    """
    from django.db.models import Q
    from accounts.models import User
    from revenue.services.statements import (
        close_period_for_user,
        previous_calendar_month,
    )
    from video_pipeline.models import VideoJob

    if period_start and period_end:
        start, end = date.fromisoformat(period_start), date.fromisoformat(period_end)
    else:
        start, end = previous_calendar_month()

    user_ids = (
        VideoJob.objects.filter(
            Q(revenue_records__date__gte=start, revenue_records__date__lt=end)
            | Q(settlements__period_start=start, settlements__period_end=end),
            is_platform_generated=True,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )

    closed = skipped = failed = 0
    for user in User.objects.filter(id__in=user_ids):
        try:
            statement = close_period_for_user(user, start, end)
        except Exception:  # noqa: BLE001 — one user's failure must not abort the batch (NFR-24)
            failed += 1
            logger.exception(
                "revenue_period_close_user_failed", extra={"user_id": str(user.id)}
            )
            continue
        if statement is not None:
            closed += 1
        else:
            skipped += 1

    result = {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "closed": closed,
        "skipped": skipped,
        "failed": failed,
    }
    logger.info("revenue_period_close_completed", extra=result)
    return result


@shared_task(name="revenue.finalize_reviewed_statements")
def finalize_reviewed_statements():
    from django.utils import timezone
    from django.db import transaction
    from revenue.models import RevenueShareStatement, StatementStatus
    from revenue.services.statements import finalize_statement

    count = 0
    for pk in RevenueShareStatement.objects.filter(
        status=StatementStatus.DRAFT, review_deadline__lte=timezone.now()
    ).values_list("pk", flat=True):
        with transaction.atomic():
            row = (
                RevenueShareStatement.objects.select_for_update(skip_locked=True)
                .filter(pk=pk, status=StatementStatus.DRAFT)
                .first()
            )
            if not row:
                continue
            # A system actor is recorded by the service for this scheduled transition.
            finalize_statement(None, row)
            count += 1
    return {"finalized": count}
