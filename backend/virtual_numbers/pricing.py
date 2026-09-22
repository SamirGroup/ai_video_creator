"""Explicit number-rental pricing, rounded per component, then summed.

The percentages are the owner's commercial configuration, not a determination
of tax liability. The applicable tax base must be confirmed before live sales.
"""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
PROFIT_PCT = Decimal("18.00")
TAX_PCT = Decimal("12.00")


def quote(base_cost, tax_basis="base"):
    base = Decimal(str(base_cost)).quantize(CENT, rounding=ROUND_HALF_UP)
    if not base.is_finite() or base < 1 or tax_basis not in ("base", "subtotal"):
        raise ValueError(
            "A base cost of at least USD 1 and valid tax basis are required."
        )
    profit = (base * PROFIT_PCT / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    net = base + profit
    tax_base = base if tax_basis == "base" else net
    tax = (tax_base * TAX_PCT / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "currency": "USD",
        "base_cost": str(base),
        "profit_pct": str(PROFIT_PCT),
        "profit": str(profit),
        "tax_pct": str(TAX_PCT),
        "tax_basis": tax_basis,
        "tax_base": str(tax_base),
        "tax": str(tax),
        "subtotal": str(net),
        "total": str(net + tax),
        "version": "cost-plus-v1",
    }
