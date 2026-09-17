"""USD accounting: tax is excluded from the 70/30 split; credits are not model tokens."""

from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone

CENT = Decimal("0.01")
CREDIT_USD = Decimal("0.0001")


def quote(plan, now=None):
    now = now or timezone.now()
    discount = (
        plan.discount_pct
        if (
            plan.discount_pct
            and (not plan.discount_starts_at or plan.discount_starts_at <= now)
            and (not plan.discount_ends_at or now < plan.discount_ends_at)
        )
        else Decimal("0")
    )
    net = (plan.price_amount * (100 - discount) / 100).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    tax = (net * plan.tax_pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    ai = (net * Decimal("0.70")).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "base": str(plan.price_amount),
        "discount_pct": str(discount),
        "net": str(net),
        "tax": str(tax),
        "total": str(net + tax),
        "ai_budget_usd": str(ai),
        "platform_usd": str(net - ai),
        "ai_credits": int(ai / CREDIT_USD),
        "credit_usd": str(CREDIT_USD),
    }
