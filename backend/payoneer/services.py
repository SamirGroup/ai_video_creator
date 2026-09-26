"""Account selection, payee onboarding and payouts."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from audit.services import record_audit_event
from payoneer import client
from payoneer.models import (
    PayeeStatus,
    PayoneerAccount,
    PayoneerPayee,
    PayoneerPayout,
    PayoutStatus,
)


def audit(action, obj, actor=None):
    record_audit_event(
        actor_type="user" if actor else "system",
        actor_id=actor.pk if actor else None,
        action=f"payoneer.{action}",
        resource_type=obj.__class__.__name__,
        resource_id=str(obj.pk),
    )


def default_checkout_account():
    account = PayoneerAccount.objects.filter(is_default_checkout=True).first()
    return account if account and account.checkout_ready else None


@transaction.atomic
def save_account(serializer, actor):
    data = serializer.validated_data
    # Only one default per role; clear the old one before the unique index sees two.
    if data.get("is_default_checkout"):
        PayoneerAccount.objects.filter(is_default_checkout=True).exclude(
            pk=getattr(serializer.instance, "pk", None)
        ).update(is_default_checkout=False)
    if data.get("is_default_payouts"):
        PayoneerAccount.objects.filter(is_default_payouts=True).exclude(
            pk=getattr(serializer.instance, "pk", None)
        ).update(is_default_payouts=False)
    account = serializer.save()
    audit("account_saved", account, actor)
    return account


def check_account(account, actor):
    results = []
    try:
        if account.checkout_enabled:
            client.check_checkout(account)
            results.append("checkout ok")
        if account.payouts_enabled:
            client.check_payouts(account)
            results.append("payouts ok")
        ok, detail = bool(results), ", ".join(results) or "Nothing is enabled"
    except APIException as exc:
        ok, detail = False, str(exc.detail)[:300]
    account.last_checked_at = timezone.now()
    account.last_check_ok, account.last_check_detail = ok, detail
    account.save(
        update_fields=["last_checked_at", "last_check_ok", "last_check_detail", "updated_at"]
    )
    audit("account_checked", account, actor)
    return account


def invite_payee(payee, actor):
    link = client.registration_link(
        payee.account,
        payee.payee_id,
        f"{settings.FRONTEND_BASE_URL}/dashboard?payoneer=registered",
    )
    audit("payee_invited", payee, actor)
    return link


def refresh_payee(payee):
    description = client.payee_status(payee.account, payee.payee_id)
    payee.provider_status = description[:60]
    lowered = description.lower()
    if lowered == "active":
        payee.status = PayeeStatus.ACTIVE
    elif lowered and lowered not in ("pending", "not registered"):
        payee.status = PayeeStatus.INACTIVE
    payee.last_checked_at = timezone.now()
    payee.save(update_fields=["provider_status", "status", "last_checked_at", "updated_at"])
    return payee


def create_payout(payee, amount, description, actor, currency="USD"):
    if not payee.account.payouts_ready:
        raise ValidationError("This Payoneer account is not set up for payouts.")
    if payee.status != PayeeStatus.ACTIVE:
        raise ValidationError("The payee has not finished Payoneer registration yet.")
    if Decimal(amount) > Decimal(settings.PAYONEER_PAYOUT_MAX_USD):
        raise ValidationError(
            f"A single payout is limited to {settings.PAYONEER_PAYOUT_MAX_USD} USD."
        )
    payout = PayoneerPayout.objects.create(
        account=payee.account,
        payee=payee,
        amount=amount,
        currency=currency,
        description=description,
        client_reference_id=uuid.uuid4().hex,
        created_by=actor,
    )
    audit("payout_created", payout, actor)
    return submit_payout(payout.pk, actor)


def submit_payout(payout_id, actor):
    """Send (or resend) a payout. Payoneer deduplicates on the reference."""
    payout = PayoneerPayout.objects.select_related("account", "payee").get(pk=payout_id)
    if payout.status != PayoutStatus.SUBMITTING:
        return payout
    client.submit_payout(
        payout.account,
        reference=payout.client_reference_id,
        payee_id=payout.payee.payee_id,
        amount=payout.amount,
        currency=payout.currency,
        description=payout.description,
    )
    with transaction.atomic():
        payout = PayoneerPayout.objects.select_for_update().get(pk=payout.pk)
        if payout.status == PayoutStatus.SUBMITTING:
            payout.status = PayoutStatus.PENDING
            payout.submitted_at = timezone.now()
            payout.save(update_fields=["status", "submitted_at", "updated_at"])
            audit("payout_submitted", payout, actor)
    return payout


STATUS_MAP = {
    "transferred": PayoutStatus.TRANSFERRED,
    "completed": PayoutStatus.TRANSFERRED,
    "cancelled": PayoutStatus.CANCELED,
    "canceled": PayoutStatus.CANCELED,
    "failed": PayoutStatus.FAILED,
    "returned": PayoutStatus.FAILED,
}


def refresh_payout(payout):
    result = client.payout_status(payout.account, payout.client_reference_id)
    payout.last_checked_at = timezone.now()
    fields = ["last_checked_at", "updated_at"]
    if result:
        raw = str(result.get("status", ""))
        payout.provider_status = raw[:60]
        payout.payout_id = str(result.get("payout_id", ""))[:120]
        payout.reason = str(
            result.get("reason_description") or result.get("cancel_reason_description") or ""
        )[:300]
        fields += ["provider_status", "payout_id", "reason"]
        new = STATUS_MAP.get(raw.lower())
        if new and payout.status in (PayoutStatus.SUBMITTING, PayoutStatus.PENDING):
            payout.status = new
            fields.append("status")
        elif payout.status == PayoutStatus.SUBMITTING:
            # Payoneer knows the reference, so the submission did land.
            payout.status = PayoutStatus.PENDING
            fields.append("status")
    payout.save(update_fields=fields)
    return payout
