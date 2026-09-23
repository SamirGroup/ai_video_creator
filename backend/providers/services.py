"""Provider selection, secret resolution and cost accounting (FR-51, FR-52, FR-84).

Everything that answers "which model do we call and what did it cost" lives here,
so no pipeline stage ever hardcodes a provider, a model id or a price.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db.models import Sum

from providers.exceptions import ProviderNotConfigured
from providers.models import ApiCredentialConfig, ApiUsageLog, CostUnit

logger = logging.getLogger("providers")

COST_QUANT = Decimal("0.000001")  # api_usage_logs.cost_usd is NUMERIC(14,6)
MONEY_QUANT = Decimal("0.0001")  # video_jobs.total_cost_usd is NUMERIC(14,4)


def _to_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def get_primary_config(service: str) -> ApiCredentialConfig:
    """Return the active `is_primary` provider row for `service`.

    Raises `ProviderNotConfigured` instead of silently falling back, because a
    silent fallback to "some other provider" would change the cost profile and
    the content policy surface without anyone noticing.
    """
    config = (
        ApiCredentialConfig.objects.filter(
            service=service, is_primary=True, is_active=True, deleted_at__isnull=True
        )
        .order_by("priority", "created_at")
        .first()
    )
    if config is None:
        raise ProviderNotConfigured(
            f"No active primary provider configured for service '{service}'. "
            "Add a row in api_credentials_config (admin -> providers)."
        )
    return config


def resolve_api_key(config: ApiCredentialConfig) -> str:
    """Dereference the config's `secret_ref`; raise if the env var is empty."""
    key = config.resolve_secret()
    if not key:
        raise ProviderNotConfigured(
            f"Provider '{config.provider}' (service={config.service}) is configured with "
            f"secret_ref='{config.secret_ref}', but that setting/environment variable is empty."
        )
    return key


def ensure_provider_ready(config):
    """Local inference needs a configured private endpoint, not a paid API key."""
    if config.provider == "ollama":
        from video_pipeline.services.ollama_client import endpoint
        endpoint()
        return
    resolve_api_key(config)


def compute_token_cost(
    config: ApiCredentialConfig,
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    provider_reported_cost=None,
) -> Decimal:
    """USD cost of one LLM call, in priority order:

    1. `provider_reported_cost` — OpenRouter returns the real billed amount in
       `usage.cost` when we ask for it; that beats any local price table.
    2. Split per-1k input/output prices from `config.config` (accurate: output
       tokens on Claude cost ~5x input tokens).
    3. Flat `unit_cost_usd` with `cost_unit=per_1k_tokens` over total tokens.
    4. Zero — with a warning, so an unpriced provider is visible in logs rather
       than quietly reporting a $0 job (FR-52 depends on this number).
    """
    if provider_reported_cost is not None:
        cost = _to_decimal(provider_reported_cost, Decimal("-1"))
        if cost >= 0:
            return cost.quantize(COST_QUANT, rounding=ROUND_HALF_UP)

    input_per_1k = _to_decimal(
        config.get_option("input_cost_per_1k_usd"), Decimal("-1")
    )
    output_per_1k = _to_decimal(
        config.get_option("output_cost_per_1k_usd"), Decimal("-1")
    )
    if input_per_1k >= 0 and output_per_1k >= 0:
        cost = (
            Decimal(prompt_tokens) / Decimal(1000) * input_per_1k
            + Decimal(completion_tokens) / Decimal(1000) * output_per_1k
        )
        return cost.quantize(COST_QUANT, rounding=ROUND_HALF_UP)

    unit_cost = _to_decimal(config.unit_cost_usd, Decimal("-1"))
    if unit_cost >= 0 and config.cost_unit == CostUnit.PER_1K_TOKENS:
        total = Decimal(prompt_tokens + completion_tokens)
        return (total / Decimal(1000) * unit_cost).quantize(
            COST_QUANT, rounding=ROUND_HALF_UP
        )

    if unit_cost >= 0 and config.cost_unit == CostUnit.PER_REQUEST:
        return unit_cost.quantize(COST_QUANT, rounding=ROUND_HALF_UP)

    logger.warning(
        "provider_cost_unpriced",
        extra={
            "service": config.service,
            "provider": config.provider,
            "model": config.model_name,
        },
    )
    return Decimal("0").quantize(COST_QUANT)


def record_api_usage(
    *,
    config: ApiCredentialConfig,
    operation: str,
    job=None,
    user=None,
    units=0,
    unit_type: str = "",
    cost_usd=Decimal("0"),
    latency_ms: int | None = None,
    http_status: int | None = None,
    success: bool = True,
    error_code: str = "",
    request_id: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> ApiUsageLog:
    """Append one `api_usage_logs` row (FR-51).

    Deliberately does not raise: cost bookkeeping must never be the reason a
    successfully generated script is thrown away. Failures are logged instead.
    """
    try:
        values = dict(
            job=job,
            user=user,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            pricing_snapshot={
                "unit_cost_usd": str(config.unit_cost_usd),
                "cost_unit": config.cost_unit,
                "input_cost_per_1k_usd": str(
                    config.get_option("input_cost_per_1k_usd", "")
                ),
                "output_cost_per_1k_usd": str(
                    config.get_option("output_cost_per_1k_usd", "")
                ),
                "pricing_source": config.get_option("pricing_source", ""),
                "pricing_verified_on": config.get_option("pricing_verified_on", ""),
            },
            service=config.service,
            provider=config.provider,
            model=config.model_name or "",
            operation=operation,
            units=_to_decimal(units).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            ),
            unit_type=unit_type or config.cost_unit or "",
            cost_usd=_to_decimal(cost_usd).quantize(COST_QUANT, rounding=ROUND_HALF_UP),
            latency_ms=latency_ms,
            http_status=http_status,
            success=success,
            error_code=error_code[:64],
            request_id=(request_id or "")[:128],
        )
        if operation == "visual_generation" and success and request_id and job:
            from django.db import transaction
            from video_pipeline.models import VideoJob

            with transaction.atomic():
                VideoJob.objects.select_for_update().get(pk=job.pk)
                existing = ApiUsageLog.objects.filter(
                    job=job,
                    provider=config.provider,
                    operation=operation,
                    request_id=request_id,
                    success=True,
                ).first()
                return existing or ApiUsageLog.objects.create(**values)
        return ApiUsageLog.objects.create(**values)
    except Exception:  # pragma: no cover - defensive
        logger.exception("api_usage_log_write_failed", extra={"operation": operation})
        raise


def job_total_cost_usd(job_id) -> Decimal:
    """Sum of every provider call booked against a job (source for FR-52 ceiling)."""
    total = ApiUsageLog.objects.filter(job_id=job_id).aggregate(total=Sum("cost_usd"))[
        "total"
    ]
    return _to_decimal(total).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def operation_cost_usd(job_id, operation: str) -> Decimal:
    """Cost of one pipeline stage for a job — written to `video_job_steps.cost_usd`
    so per-stage spend is visible in the admin job monitor (FR-80, SPEC 5.12).
    """
    total = ApiUsageLog.objects.filter(job_id=job_id, operation=operation).aggregate(
        total=Sum("cost_usd")
    )["total"]
    return _to_decimal(total).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
