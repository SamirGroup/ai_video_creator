"""Generation gates (FR-32, FR-70a, FR-26/FR-70b, AC-3).

    from contracts.gates import assert_generation_allowed, GenerationBlocked
    assert_generation_allowed(user)   # raises a 403 problem+json exception

Checked in order (first failure wins):
1. subscription usable — `trialing`/`active` and not paused for dunning
   (`SUBSCRIPTION_INACTIVE`);
2. the currently active contract version is signed (`CONTRACT_NOT_SIGNED`,
   also raised when a newer version needs re-consent, FR-28);
3. a saved payment method exists (`PAYMENT_METHOD_REQUIRED`, FR-70a) — waived
   for the Free plan, which has no revenue share (A-20).

Quota is a separate concern: see `billing.quota`.
"""
from __future__ import annotations

from dataclasses import dataclass

from rest_framework import status
from rest_framework.exceptions import APIException

from billing.models import Subscription, SubscriptionStatus
from billing.quota import FREE_PLAN_CODE, QUOTA_GRANTING_STATUSES
from contracts.models import Contract, ContractStatus, ContractVersion


class GenerationBlocked(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "GENERATION_BLOCKED"
    default_detail = "Video generation is not allowed for this account."


class SubscriptionInactive(GenerationBlocked):
    default_code = "SUBSCRIPTION_INACTIVE"
    default_detail = "Your subscription is not active. Activate a plan to generate videos."


class ContractNotSigned(GenerationBlocked):
    default_code = "CONTRACT_NOT_SIGNED"
    default_detail = "Please sign the current creator agreement before generating videos."


class PaymentMethodRequired(GenerationBlocked):
    default_code = "PAYMENT_METHOD_REQUIRED"
    default_detail = "Please save a payment method before generating videos."


@dataclass(frozen=True)
class GenerationEligibility:
    allowed: bool
    code: str | None
    detail: str | None
    subscription_active: bool
    contract_signed: bool
    payment_method_saved: bool


def get_active_contract_version() -> ContractVersion | None:
    return ContractVersion.objects.filter(is_active=True).order_by("-effective_from").first()


def get_signed_contract(user, version: ContractVersion | None = None) -> Contract | None:
    """The creator's active contract for `version` (default: current active version)."""
    version = version or get_active_contract_version()
    if version is None:
        return None
    return (
        Contract.objects.filter(user=user, contract_version=version, status=ContractStatus.ACTIVE)
        .order_by("-signed_at")
        .first()
    )


def _subscription(user) -> Subscription | None:
    return Subscription.objects.filter(user=user).select_related("plan").first()


def check_generation_eligibility(user) -> GenerationEligibility:
    subscription = _subscription(user)
    plan_code = subscription.plan.code if subscription else None
    subscription_ok = subscription is not None and subscription.status in QUOTA_GRANTING_STATUSES
    paused = subscription is not None and subscription.revenue_share_paused
    contract_ok = get_signed_contract(user) is not None
    payment_ok = bool(subscription and subscription.default_payment_method_id)
    payment_required = plan_code != FREE_PLAN_CODE

    if subscription is None:
        return GenerationEligibility(False, SubscriptionInactive.default_code, "No subscription found. Choose a plan to get started.", False, contract_ok, payment_ok)
    if not subscription_ok:
        detail = {
            SubscriptionStatus.PAST_DUE: "Your subscription is past due. Update your payment method to resume generation.",
            SubscriptionStatus.SUSPENDED: "Your subscription is suspended. Settle the outstanding balance to resume generation.",
        }.get(subscription.status, SubscriptionInactive.default_detail)
        return GenerationEligibility(False, SubscriptionInactive.default_code, detail, False, contract_ok, payment_ok)
    if paused:
        return GenerationEligibility(
            False,
            SubscriptionInactive.default_code,
            "Video generation is paused because a service-fee invoice is overdue (FR-70b).",
            False,
            contract_ok,
            payment_ok,
        )
    if not contract_ok:
        return GenerationEligibility(False, ContractNotSigned.default_code, ContractNotSigned.default_detail, True, False, payment_ok)
    if payment_required and not payment_ok:
        return GenerationEligibility(False, PaymentMethodRequired.default_code, PaymentMethodRequired.default_detail, True, True, False)
    return GenerationEligibility(True, None, None, True, True, payment_ok)


_EXC_BY_CODE = {
    SubscriptionInactive.default_code: SubscriptionInactive,
    ContractNotSigned.default_code: ContractNotSigned,
    PaymentMethodRequired.default_code: PaymentMethodRequired,
}


def assert_generation_allowed(user) -> GenerationEligibility:
    """Raise the matching 403 `GenerationBlocked` subclass, or return the eligibility."""
    eligibility = check_generation_eligibility(user)
    if not eligibility.allowed:
        raise _EXC_BY_CODE[eligibility.code](eligibility.detail)
    return eligibility
