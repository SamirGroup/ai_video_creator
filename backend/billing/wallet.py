from decimal import Decimal
from django.db import transaction
from rest_framework.exceptions import PermissionDenied
from billing.models import AIWallet, AIWalletEntry, AIBudgetReservation


def enabled(user):
    subscription = getattr(user, "subscription", None)
    return bool(subscription and subscription.plan.ai_budget_enabled)


@transaction.atomic
def credit_payment(user, reference, net_usd, **details):
    amount = (Decimal(str(net_usd)) * Decimal("0.70")).quantize(Decimal("0.000001"))
    if amount <= 0:
        return
    details = {
        **details,
        "net_usd": str(net_usd),
        "ai_usd": str(amount),
        "platform_usd": str(Decimal(str(net_usd)) - amount),
        "accounting_mode": "provider_credit",
    }
    wallet, _ = AIWallet.objects.get_or_create(user=user)
    wallet = AIWallet.objects.select_for_update().get(pk=wallet.pk)
    _, created = AIWalletEntry.objects.get_or_create(
        reference=reference,
        defaults={
            "wallet": wallet,
            "amount_usd": amount,
            "kind": "payment",
            "details": details,
        },
    )
    if created:
        wallet.balance_usd += amount
        wallet.save(update_fields=["balance_usd", "updated_at"])
    if reference.startswith("stripe:"):
        from billing.models import WebhookEvent

        for event in WebhookEvent.objects.filter(
            event_type="charge.refunded",
            status="processed",
            payload__data__object__invoice=reference[7:],
        ):
            reverse_stripe_refund(event.payload["data"]["object"])


@transaction.atomic
def reserve_job(job):
    if (
        not enabled(job.user)
        and not AIBudgetReservation.objects.filter(job=job).exists()
    ):
        return
    from django.conf import settings

    wallet, _ = AIWallet.objects.get_or_create(user=job.user)
    wallet = AIWallet.objects.select_for_update().get(pk=wallet.pk)
    reservation = AIBudgetReservation.objects.filter(job=job).first()
    if wallet.balance_usd < wallet.reserved_usd:
        raise PermissionDenied("AI wallet is overdrawn or a payment was refunded.")
    if reservation and reservation.remaining_usd > 0:
        return
    from providers.services import job_total_cost_usd

    ceiling = Decimal(
        str(
            job.user.subscription.plan.features.get(
                "job_budget_usd", settings.JOB_COST_CEILING_USD
            )
        )
    ) - job_total_cost_usd(job.pk)
    if ceiling <= 0 or wallet.balance_usd - wallet.reserved_usd < ceiling:
        raise PermissionDenied(
            "Insufficient AI credit for the remaining job cost ceiling."
        )
    if reservation:
        reservation.remaining_usd = ceiling
        reservation.save(update_fields=["remaining_usd"])
    else:
        AIBudgetReservation.objects.create(
            job=job, wallet=wallet, remaining_usd=ceiling
        )
    wallet.reserved_usd += ceiling
    wallet.save(update_fields=["reserved_usd", "updated_at"])


@transaction.atomic
def debit_usage(log):
    if not log.user_id or (
        not enabled(log.user)
        and not AIWalletEntry.objects.filter(
            wallet__user_id=log.user_id, kind="payment"
        ).exists()
    ):
        return
    wallet, _ = AIWallet.objects.get_or_create(user=log.user)
    wallet = AIWallet.objects.select_for_update().get(pk=wallet.pk)
    _, created = AIWalletEntry.objects.get_or_create(
        reference=f"usage:{log.pk}",
        defaults={
            "wallet": wallet,
            "amount_usd": -log.cost_usd,
            "kind": "usage",
            "details": {
                "provider": log.provider,
                "model": log.model,
                "units": str(log.units),
                "unit_type": log.unit_type,
                "job_id": str(log.job_id),
            },
        },
    )
    if not created:
        return
    wallet.balance_usd -= log.cost_usd
    reservation = (
        AIBudgetReservation.objects.filter(job_id=log.job_id).first()
        if log.job_id
        else None
    )
    if reservation:
        released = min(reservation.remaining_usd, log.cost_usd)
        reservation.remaining_usd -= released
        reservation.save(update_fields=["remaining_usd"])
        wallet.reserved_usd -= released
    wallet.save(update_fields=["balance_usd", "reserved_usd", "updated_at"])


@transaction.atomic
def release_job(job):
    reservation = AIBudgetReservation.objects.filter(job=job).first()
    if not reservation:
        return
    wallet = AIWallet.objects.select_for_update().get(pk=reservation.wallet_id)
    reservation.refresh_from_db()
    wallet.reserved_usd -= reservation.remaining_usd
    wallet.save(update_fields=["reserved_usd", "updated_at"])
    reservation.remaining_usd = 0
    reservation.save(update_fields=["remaining_usd"])


def ensure_job_call_budget(job, cost):
    if (
        not enabled(job.user)
        and not AIBudgetReservation.objects.filter(job=job).exists()
    ):
        return
    reservation = AIBudgetReservation.objects.select_related("wallet").get(job=job)
    if (
        cost <= 0
        or cost > reservation.remaining_usd
        or reservation.wallet.balance_usd < reservation.wallet.reserved_usd
    ):
        raise PermissionDenied(
            "The next provider call exceeds the remaining AI budget, or its price is not configured."
        )


@transaction.atomic
def reverse_stripe_refund(charge):
    invoice_id = charge.get("invoice")
    if isinstance(invoice_id, dict):
        invoice_id = invoice_id.get("id")
    grant = AIWalletEntry.objects.filter(
        reference=f"stripe:{invoice_id}", kind="payment"
    ).first()
    if not grant or not charge.get("amount"):
        return
    wallet = AIWallet.objects.select_for_update().get(pk=grant.wallet_id)
    from django.db.models import Sum

    prior = -(
        wallet.entries.filter(kind="refund", details__charge_id=charge["id"]).aggregate(
            value=Sum("amount_usd")
        )["value"]
        or Decimal("0")
    )
    target = min(
        grant.amount_usd,
        grant.amount_usd
        * Decimal(charge.get("amount_refunded", 0))
        / Decimal(charge["amount"]),
    )
    difference = (target - prior).quantize(Decimal("0.000001"))
    if difference <= 0:
        return
    AIWalletEntry.objects.create(
        wallet=wallet,
        reference=f"refund:{charge['id']}:{charge['amount_refunded']}",
        amount_usd=-difference,
        kind="refund",
        details={"charge_id": charge["id"], "invoice_id": invoice_id},
    )
    wallet.balance_usd -= difference
    wallet.save(update_fields=["balance_usd", "updated_at"])


@transaction.atomic
def hold_operation(user, reference, amount):
    if not enabled(user):
        return
    from billing.models import AIWalletHold

    wallet, _ = AIWallet.objects.get_or_create(user=user)
    wallet = AIWallet.objects.select_for_update().get(pk=wallet.pk)
    if AIWalletHold.objects.filter(reference=reference).exists():
        raise PermissionDenied("This AI operation has already been reserved.")
    if amount <= 0 or wallet.balance_usd - wallet.reserved_usd < amount:
        raise PermissionDenied("Insufficient AI balance or missing provider price.")
    AIWalletHold.objects.create(wallet=wallet, reference=reference, amount_usd=amount)
    wallet.reserved_usd += amount
    wallet.save(update_fields=["reserved_usd", "updated_at"])


@transaction.atomic
def release_operation(reference):
    from billing.models import AIWalletHold

    hold = AIWalletHold.objects.filter(reference=reference).first()
    if not hold:
        return
    wallet = AIWallet.objects.select_for_update().get(pk=hold.wallet_id)
    hold.refresh_from_db()
    if hold.released:
        return
    wallet.reserved_usd -= hold.amount_usd
    wallet.save(update_fields=["reserved_usd", "updated_at"])
    hold.released = True
    hold.save(update_fields=["released"])
