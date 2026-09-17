"""Per-job spend accounting shared by stages 3–6 (FR-51, FR-52).

`script_generation` keeps its own private ceiling check for historical reasons;
every later stage goes through this module so the rule lives in one place:

* `unit_cost(config, units, unit)` — price one provider call from the
  `api_credentials_config` row (never from code).
* `refresh_job_cost(job)` — recompute `video_jobs.total_cost_usd` from
  `api_usage_logs` (the single source of truth).
* `check_cost_ceiling(job)` — raise `CostCeilingExceeded` when the running
  total passed `settings.JOB_COST_CEILING_USD`. Called **before** every paid
  provider call in the expensive stages (visuals), and after each stage.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings

from providers.models import ApiCredentialConfig
from providers.services import COST_QUANT, job_total_cost_usd
from video_pipeline.services.exceptions import CostCeilingExceeded

logger = logging.getLogger("video_pipeline.cost")


def _decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def cost_ceiling_usd() -> Decimal:
    ceiling = _decimal(getattr(settings, "JOB_COST_CEILING_USD", "0"), Decimal("0"))
    return ceiling if ceiling > 0 else Decimal("0")


def unit_cost(config: ApiCredentialConfig, units, *, expected_unit: str) -> Decimal:
    """USD for `units` of work against `config`.

    Priority: a matching `unit_cost_usd`/`cost_unit` pair on the row, then the
    `config.<expected_unit>_cost_usd` JSON option, then zero with a warning so an
    unpriced provider is visible instead of silently reporting a free job.
    """
    quantity = _decimal(units)
    row_price = _decimal(config.unit_cost_usd, Decimal("-1"))
    if row_price >= 0 and config.cost_unit == expected_unit:
        return (quantity * row_price).quantize(COST_QUANT, rounding=ROUND_HALF_UP)

    option_price = _decimal(
        config.get_option(f"{expected_unit}_cost_usd"), Decimal("-1")
    )
    if option_price >= 0:
        return (quantity * option_price).quantize(COST_QUANT, rounding=ROUND_HALF_UP)

    logger.warning(
        "provider_cost_unpriced",
        extra={
            "service": config.service,
            "provider": config.provider,
            "expected_unit": expected_unit,
            "cost_unit": config.cost_unit,
        },
    )
    return Decimal("0").quantize(COST_QUANT)


def refresh_job_cost(job) -> Decimal:
    total = job_total_cost_usd(job.pk)
    if job.total_cost_usd != total:
        job.total_cost_usd = total
        job.save(update_fields=["total_cost_usd", "updated_at"])
    return total


def check_cost_ceiling(job, *, refresh: bool = True) -> Decimal:
    """Enforce FR-52. Returns the current total when under the ceiling."""
    total = refresh_job_cost(job) if refresh else _decimal(job.total_cost_usd)
    ceiling = cost_ceiling_usd()
    if ceiling > 0 and total > ceiling:
        raise CostCeilingExceeded(
            f"Job {job.pk} spent ${total} which exceeds the ${ceiling} per-job ceiling (FR-52)."
        )
    # Revisions share one budget, so splitting work across replacement jobs
    # cannot reset the spending limit.
    if job.parent_job_id:
        from django.db.models import Sum
        from video_pipeline.models import VideoJob

        root = job
        while root.parent_job_id:
            root = root.parent_job
        descendants = VideoJob.objects.filter(revision_origin__root_job=root)
        spent = root.total_cost_usd + (
            descendants.aggregate(total=Sum("total_cost_usd"))["total"] or Decimal("0")
        )
        budget = _decimal(getattr(settings, "MODERATION_REVISION_BUDGET_USD", "30"))
        if budget <= 0 or spent >= budget:
            raise CostCeilingExceeded(
                "The shared moderation revision budget is exhausted."
            )
    return total
