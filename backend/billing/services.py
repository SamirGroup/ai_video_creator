"""Stripe integration services for the `billing` app (FR-21..FR-27, FR-70,
FR-70a, FR-70b).

All Stripe API calls and webhook side-effects go through this module so
views stay thin and every state transition (subscription status, invoice,
ledger entry, audit log) is written from one place. Webhook handlers work
off the event payload itself rather than making extra Stripe API calls, to
keep the webhook endpoint fast and its failure surface small.
"""

from __future__ import annotations

import logging
from datetime import timedelta, timezone as dt_timezone
from decimal import ROUND_HALF_UP, Decimal

import stripe
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.services import record_audit_event
from billing.models import (
    Plan,
    Subscription,
    SubscriptionStatus,
    WebhookEvent,
    WebhookEventStatus,
    WebhookProvider,
)

logger = logging.getLogger("billing.services")

DUNNING_GRACE_PERIOD_DAYS = 7  # FR-26, FR-70b
MIN_REVENUE_SHARE_INVOICE_AMOUNT = Decimal("10.00")  # A-10


class RevenueShareInvoiceError(Exception):
    """Raised when `create_revenue_share_invoice` cannot proceed (missing
    Stripe customer, missing FR-70a saved payment method, or below the A-10
    minimum invoiceable threshold).
    """


def _stripe() -> "stripe":
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def _epoch_to_datetime(epoch):
    if epoch is None:
        return None
    return timezone.datetime.fromtimestamp(epoch, tz=dt_timezone.utc)


def _map_stripe_subscription_status(stripe_status: str) -> str:
    return {
        "trialing": SubscriptionStatus.TRIALING,
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "unpaid": SubscriptionStatus.SUSPENDED,
        "canceled": SubscriptionStatus.CANCELED,
        "incomplete": SubscriptionStatus.PAST_DUE,
        "incomplete_expired": SubscriptionStatus.EXPIRED,
        "paused": SubscriptionStatus.SUSPENDED,
    }.get(stripe_status, SubscriptionStatus.ACTIVE)


def _map_stripe_invoice_status(stripe_status: str) -> str:
    from revenue.models import InvoiceStatus

    return {
        "draft": InvoiceStatus.DRAFT,
        "open": InvoiceStatus.OPEN,
        "paid": InvoiceStatus.PAID,
        "uncollectible": InvoiceStatus.UNCOLLECTIBLE,
        "void": InvoiceStatus.VOID,
    }.get(stripe_status, InvoiceStatus.OPEN)


# ---------------------------------------------------------------------------
# Customer / Checkout / Portal (FR-22)
# ---------------------------------------------------------------------------


def get_or_create_stripe_customer(user, subscription: Subscription) -> str:
    if subscription.stripe_customer_id:
        return subscription.stripe_customer_id
    customer = _stripe().Customer.create(
        email=user.email, metadata={"user_id": str(user.id)}
    )
    subscription.stripe_customer_id = customer.id
    subscription.save(update_fields=["stripe_customer_id", "updated_at"])
    return customer.id


def create_checkout_session(*, user, plan: Plan, success_url: str, cancel_url: str):
    """FR-22: Stripe Checkout Session for a subscription plan."""
    subscription, _ = Subscription.objects.get_or_create(
        user=user, defaults={"plan": plan}
    )
    customer_id = get_or_create_stripe_customer(user, subscription)

    line_items = [{"price": plan.stripe_price_id, "quantity": 1}]
    if plan.ai_budget_enabled:
        from billing.economics import quote

        pricing = quote(plan)
        tax = _stripe().TaxRate.create(
            display_name="Tax",
            inclusive=False,
            percentage=float(plan.tax_pct),
            idempotency_key=f"plan-tax-exclusive-{plan.tax_pct}",
        )
        line_items = [
            {
                "price_data": {
                    "currency": plan.currency.lower(),
                    "unit_amount": int(Decimal(pricing["net"]) * 100),
                    "product_data": {"name": plan.name},
                    "recurring": {
                        "interval": "month",
                        "interval_count": 6
                        if plan.billing_interval == "six_months"
                        else 1,
                    },
                },
                "quantity": 1,
                "tax_rates": [tax.id],
            }
        ]
    return _stripe().checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(user.id),
        subscription_data={
            "metadata": {"user_id": str(user.id), "plan_code": plan.code}
        },
        payment_method_collection="always",
        metadata={"user_id": str(user.id), "plan_code": plan.code},
    )


def create_portal_session(*, user, return_url: str):
    """FR-22: Stripe Customer Portal session for self-service plan/payment-method management."""
    subscription = Subscription.objects.filter(user=user).first()
    if subscription is None or not subscription.stripe_customer_id:
        raise ValueError(
            "User has no Stripe customer yet — create a checkout session first."
        )
    return _stripe().billing_portal.Session.create(
        customer=subscription.stripe_customer_id, return_url=return_url
    )


# ---------------------------------------------------------------------------
# Webhook signature verification + idempotent dispatch (FR-25, NFR-5, AC-8)
# ---------------------------------------------------------------------------


def construct_stripe_event(payload: bytes, sig_header: str):
    """Verifies the Stripe-Signature header. Raises ValueError (bad payload) or
    stripe.error.SignatureVerificationError (bad signature) — both are 400s at
    the view layer, and neither leaves any state changed (AC-8).
    """
    return _stripe().Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )


def record_and_dispatch_webhook_event(event) -> WebhookEvent:
    """FR-25: persists the event keyed by `event_id` before any side effect, so
    Stripe's at-least-once delivery is safe to retry. A duplicate `event_id`
    is recognized via the DB unique constraint (race-safe under concurrent
    deliveries) and returned as-is without re-running any handler.
    """
    event_id = event["id"]
    event_type = event["type"]
    payload = event.to_dict()

    try:
        with transaction.atomic():
            webhook_event = WebhookEvent.objects.create(
                provider=WebhookProvider.STRIPE,
                event_id=event_id,
                event_type=event_type,
                payload=payload,
                signature_verified=True,
                status=WebhookEventStatus.RECEIVED,
            )
    except IntegrityError:
        logger.info("stripe_webhook_duplicate_ignored", extra={"event_id": event_id})
        return WebhookEvent.objects.get(
            provider=WebhookProvider.STRIPE, event_id=event_id
        )

    handler = _EVENT_HANDLERS.get(event_type)
    try:
        if handler is not None:
            # Stripe's `StripeObject` (this library's newer major versions) only
            # supports item access for known keys — it does NOT implement dict's
            # `.get()`. Every handler below is written against a plain dict, so
            # convert once here rather than in each handler.
            handler(event["data"]["object"].to_dict())
        webhook_event.status = WebhookEventStatus.PROCESSED
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "processed_at"])
    except Exception as exc:  # noqa: BLE001 — must surface to the caller so the view 500s and Stripe retries
        logger.exception(
            "stripe_webhook_handler_failed",
            extra={"event_id": event_id, "event_type": event_type},
        )
        webhook_event.status = WebhookEventStatus.FAILED
        webhook_event.error = str(exc)
        webhook_event.save(update_fields=["status", "error"])
        raise

    return webhook_event


def _resolve_subscription_for_stripe_object(obj: dict) -> Subscription | None:
    stripe_subscription_id = (
        obj.get("id")
        if obj.get("object") == "subscription"
        else obj.get("subscription")
    )
    customer_id = obj.get("customer")

    subscription = None
    if stripe_subscription_id:
        subscription = Subscription.objects.filter(
            stripe_subscription_id=stripe_subscription_id
        ).first()
    if subscription is None and customer_id:
        subscription = Subscription.objects.filter(
            stripe_customer_id=customer_id
        ).first()
    return subscription


def _handle_checkout_session_completed(session: dict) -> None:
    """FR-22: activates the local `Subscription` once Stripe confirms checkout.
    Detailed period/payment-method sync happens on the `customer.subscription.*`
    events that follow, straight from their own payload.
    """
    # Saving a card is not a subscription purchase. Delayed payments must
    # become paid before granting access.
    if session.get("mode") == "setup" or session.get("payment_status") == "unpaid":
        return

    metadata = session.get("metadata") or {}
    user_id = metadata.get("user_id") or session.get("client_reference_id")
    if not user_id:
        logger.warning(
            "checkout_session_completed_missing_user_id",
            extra={"session_id": session.get("id")},
        )
        return

    subscription = Subscription.objects.filter(user_id=user_id).first()
    if subscription is None:
        logger.warning(
            "checkout_session_completed_no_local_subscription",
            extra={"user_id": user_id},
        )
        return

    plan_code = metadata.get("plan_code")
    if plan_code:
        plan = Plan.objects.filter(code=plan_code).first()
        if plan is not None:
            subscription.plan = plan

    if session.get("customer"):
        subscription.stripe_customer_id = session["customer"]
    if session.get("subscription"):
        subscription.stripe_subscription_id = session["subscription"]
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.save()

    record_audit_event(
        actor_type="system",
        action="subscription.activated",
        resource_type="subscription",
        resource_id=str(subscription.id),
        after={
            "plan": subscription.plan.code,
            "stripe_subscription_id": subscription.stripe_subscription_id,
        },
    )


def _handle_invoice_paid(invoice: dict) -> None:
    """FR-25, FR-26: a successful payment always clears any past_due/grace state."""
    subscription = _resolve_subscription_for_stripe_object(invoice)
    if subscription is None:
        logger.warning(
            "invoice_paid_no_local_subscription",
            extra={"stripe_invoice_id": invoice.get("id")},
        )
        return
    if (
        subscription.plan.ai_budget_enabled
        and invoice.get("currency") == "usd"
        and invoice.get("total_excluding_tax") is not None
        and invoice.get("amount_paid", 0) >= invoice.get("total", 0)
    ):
        from billing.wallet import credit_payment

        credit_payment(
            subscription.user,
            f"stripe:{invoice['id']}",
            Decimal(str(invoice["total_excluding_tax"])) / 100,
            plan_code=subscription.plan.code,
        )

    subscription.status = SubscriptionStatus.ACTIVE
    subscription.grace_period_ends_at = None
    subscription.save(update_fields=["status", "grace_period_ends_at", "updated_at"])

    _record_ledger_entry(
        subscription=subscription,
        amount=Decimal(invoice.get("amount_paid", 0)) / 100,
        currency=(invoice.get("currency") or "usd").upper(),
        description=f"Stripe invoice {invoice.get('id')} paid",
    )
    record_audit_event(
        actor_type="system",
        action="invoice.paid",
        resource_type="subscription",
        resource_id=str(subscription.id),
        metadata={"stripe_invoice_id": invoice.get("id")},
    )


def _handle_invoice_payment_failed(invoice: dict) -> None:
    """FR-26, FR-70b: 3 Stripe Smart Retries -> 7 day grace -> past_due."""
    subscription = _resolve_subscription_for_stripe_object(invoice)
    if subscription is None:
        logger.warning(
            "invoice_payment_failed_no_local_subscription",
            extra={"stripe_invoice_id": invoice.get("id")},
        )
        return

    if subscription.status == SubscriptionStatus.ACTIVE:
        subscription.status = SubscriptionStatus.PAST_DUE
        subscription.grace_period_ends_at = timezone.now() + timedelta(
            days=DUNNING_GRACE_PERIOD_DAYS
        )
    subscription.save(update_fields=["status", "grace_period_ends_at", "updated_at"])

    record_audit_event(
        actor_type="system",
        action="invoice.payment_failed",
        resource_type="subscription",
        resource_id=str(subscription.id),
        metadata={"stripe_invoice_id": invoice.get("id")},
    )


def _handle_subscription_updated(stripe_subscription: dict) -> None:
    subscription = _resolve_subscription_for_stripe_object(stripe_subscription)
    if subscription is None:
        logger.warning(
            "subscription_updated_no_local_subscription",
            extra={"stripe_subscription_id": stripe_subscription.get("id")},
        )
        return

    subscription.stripe_subscription_id = stripe_subscription.get(
        "id", subscription.stripe_subscription_id
    )
    subscription.status = _map_stripe_subscription_status(
        stripe_subscription.get("status")
    )
    subscription.current_period_start = _epoch_to_datetime(
        stripe_subscription.get("current_period_start")
    )
    subscription.current_period_end = _epoch_to_datetime(
        stripe_subscription.get("current_period_end")
    )
    subscription.cancel_at_period_end = bool(
        stripe_subscription.get("cancel_at_period_end")
    )

    default_pm = stripe_subscription.get("default_payment_method")
    if default_pm:
        subscription.default_payment_method_id = (
            default_pm
            if isinstance(default_pm, str)
            else (default_pm.get("id") or subscription.default_payment_method_id)
        )
    if subscription.status == SubscriptionStatus.ACTIVE:
        subscription.grace_period_ends_at = None
    subscription.save()

    record_audit_event(
        actor_type="system",
        action="subscription.updated",
        resource_type="subscription",
        resource_id=str(subscription.id),
        after={"status": subscription.status},
    )


def _handle_subscription_deleted(stripe_subscription: dict) -> None:
    subscription = _resolve_subscription_for_stripe_object(stripe_subscription)
    if subscription is None:
        return
    subscription.status = SubscriptionStatus.CANCELED
    subscription.canceled_at = timezone.now()
    subscription.save(update_fields=["status", "canceled_at", "updated_at"])

    record_audit_event(
        actor_type="system",
        action="subscription.canceled",
        resource_type="subscription",
        resource_id=str(subscription.id),
    )


_EVENT_HANDLERS = {
    "checkout.session.completed": _handle_checkout_session_completed,
    "invoice.paid": _handle_invoice_paid,
    "invoice.payment_failed": _handle_invoice_payment_failed,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
}


def _record_ledger_entry(
    *, subscription: Subscription, amount: Decimal, currency: str, description: str
) -> None:
    from revenue.models import LedgerDirection, LedgerEntry, LedgerRefType

    LedgerEntry.objects.create(
        user=subscription.user,
        ref_type=LedgerRefType.SUBSCRIPTION,
        ref_id=subscription.id,
        direction=LedgerDirection.CREDIT,
        amount=amount,
        currency=currency,
        description=description,
        occurred_at=timezone.now(),
    )


# ---------------------------------------------------------------------------
# Revenue-share service-fee invoicing (Q1 decision, FR-70, FR-70a, FR-70b)
# ---------------------------------------------------------------------------


def create_revenue_share_invoice(user, statement):
    """FR-70 (Q1 TASDIQLANGAN QAROR — service-fee model): charges the
    creator's saved Stripe payment method for the platform's share of a
    finalized revenue-share statement ("AI production & revenue-share service
    fee"), never a direct AdSense revenue split (Risk R-1).

    Returns the created `revenue.models.Invoice` row. Not yet called by
    anything (the `revenue` app's period-close job is a separate piece of
    work) — this function is complete and independently testable so that
    integration is a one-line call once that job exists.

    Raises RevenueShareInvoiceError if:
      - the user has no Stripe customer yet;
      - FR-70a's mandatory saved payment method is missing (should never
        happen if the contract-signing flow enforced it correctly — fail
        loudly rather than silently skip billing);
      - the amount is below the A-10 minimum ($10) — the caller is expected
        to mark the statement `carried_forward` instead of invoicing it.
    """
    from revenue.models import (
        Invoice,
        InvoiceKind,
        LedgerDirection,
        LedgerEntry,
        LedgerRefType,
    )

    subscription = Subscription.objects.filter(user=user).first()
    if subscription is None or not subscription.stripe_customer_id:
        raise RevenueShareInvoiceError(
            "User has no Stripe customer — cannot invoice revenue share."
        )
    if not subscription.default_payment_method_id:
        raise RevenueShareInvoiceError(
            "User has no saved default payment method (FR-70a requires one before the contract is active)."
        )

    amount = statement.platform_share_amount
    if amount < MIN_REVENUE_SHARE_INVOICE_AMOUNT:
        raise RevenueShareInvoiceError(
            f"Amount {amount} is below the minimum invoiceable threshold "
            f"({MIN_REVENUE_SHARE_INVOICE_AMOUNT}) — carry it forward instead (A-10)."
        )

    amount_cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    currency = statement.currency.lower()

    _stripe().InvoiceItem.create(
        customer=subscription.stripe_customer_id,
        amount=amount_cents,
        currency=currency,
        description=(
            "AI production & revenue-share service fee — "
            f"{statement.period_start.isoformat()} to {statement.period_end.isoformat()}"
        ),
        metadata={"statement_id": str(statement.id), "user_id": str(user.id)},
    )
    stripe_invoice = _stripe().Invoice.create(
        customer=subscription.stripe_customer_id,
        collection_method="charge_automatically",
        default_payment_method=subscription.default_payment_method_id,
        auto_advance=True,
        metadata={"statement_id": str(statement.id), "kind": "revenue_share"},
    )
    stripe_invoice = stripe_invoice.finalize_invoice()
    try:
        stripe_invoice = stripe_invoice.pay()
    except stripe.error.StripeError as exc:
        # FR-70b: charge failed here synchronously — Stripe will also still
        # fire `invoice.payment_failed`/Smart Retries for this invoice, which
        # is what actually drives the dunning/pause state machine above.
        logger.warning(
            "revenue_share_invoice_charge_failed",
            extra={"statement_id": str(statement.id), "error": str(exc)},
        )

    invoice = Invoice.objects.create(
        user=user,
        statement=statement,
        subscription=subscription,
        kind=InvoiceKind.REVENUE_SHARE,
        amount=amount,
        currency=statement.currency,
        stripe_invoice_id=stripe_invoice.id,
        status=_map_stripe_invoice_status(stripe_invoice.status),
        due_at=timezone.now(),
        paid_at=timezone.now() if stripe_invoice.status == "paid" else None,
        attempts=1,
    )

    LedgerEntry.objects.create(
        user=user,
        ref_type=LedgerRefType.INVOICE,
        ref_id=invoice.id,
        direction=LedgerDirection.DEBIT,
        amount=amount,
        currency=statement.currency,
        description=f"Revenue-share service fee invoice {invoice.id}",
        occurred_at=timezone.now(),
    )

    record_audit_event(
        actor_type="system",
        action="invoice.created",
        resource_type="invoice",
        resource_id=str(invoice.id),
        after={
            "kind": "revenue_share",
            "amount": str(amount),
            "status": invoice.status,
        },
    )
    return invoice


# --- Track A ---------------------------------------------------------------
# FR-70a: mandatory saved payment method, collected via a Stripe SetupIntent
# during the contract-signing flow. `setup_intent.succeeded` (and the
# customer's default payment method) lands in `subscription.default_payment_method_id`,
# which `contracts.gates.assert_generation_allowed` requires before any job runs.
# ---------------------------------------------------------------------------


def create_setup_intent(*, user):
    """Create an off-session SetupIntent for the creator's Stripe customer.

    Returns the Stripe SetupIntent (its `client_secret` is what the frontend
    needs for `stripe.confirmSetup`). A subscription row is created on the
    Free plan if the creator has none yet, so the customer id has a home.
    """
    subscription = Subscription.objects.filter(user=user).select_related("plan").first()
    if subscription is None:
        plan = (
            Plan.objects.filter(code="free").first()
            or Plan.objects.filter(is_active=True).order_by("sort_order").first()
        )
        if plan is None:
            raise ValueError(
                "No plan is configured — seed `plans` before collecting payment methods."
            )
        subscription = Subscription.objects.create(user=user, plan=plan)
    customer_id = get_or_create_stripe_customer(user, subscription)

    intent = _stripe().SetupIntent.create(
        customer=customer_id,
        usage="off_session",
        payment_method_types=["card"],
        metadata={"user_id": str(user.id), "purpose": "revenue_share_service_fee"},
    )
    record_audit_event(
        actor_type="user",
        actor_id=user.id,
        action="billing.setup_intent.created",
        resource_type="subscription",
        resource_id=str(subscription.id),
        metadata={"setup_intent_id": intent.id},
    )
    return intent


def _handle_setup_intent_succeeded(setup_intent: dict) -> None:
    """FR-70a: persist the saved payment method and make it the customer default."""
    customer_id = setup_intent.get("customer")
    payment_method = setup_intent.get("payment_method")
    if isinstance(payment_method, dict):
        payment_method = payment_method.get("id")
    if not customer_id or not payment_method:
        logger.warning(
            "setup_intent_succeeded_missing_fields",
            extra={"setup_intent_id": setup_intent.get("id")},
        )
        return

    subscription = Subscription.objects.filter(stripe_customer_id=customer_id).first()
    if subscription is None:
        user_id = (setup_intent.get("metadata") or {}).get("user_id")
        subscription = (
            Subscription.objects.filter(user_id=user_id).first() if user_id else None
        )
    if subscription is None:
        logger.warning(
            "setup_intent_succeeded_no_local_subscription",
            extra={"customer_id": customer_id},
        )
        return

    before = subscription.default_payment_method_id
    subscription.default_payment_method_id = payment_method
    subscription.save(update_fields=["default_payment_method_id", "updated_at"])

    # Best effort: make it the customer's default for future invoices too. The
    # local state above is the source of truth for the gate, so a Stripe error
    # here must not fail the webhook (it would only cause a retry storm).
    try:
        _stripe().Customer.modify(
            customer_id, invoice_settings={"default_payment_method": payment_method}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "setup_intent_customer_default_update_failed",
            extra={"customer_id": customer_id, "error": str(exc)},
        )

    record_audit_event(
        actor_type="system",
        action="billing.payment_method.saved",
        resource_type="subscription",
        resource_id=str(subscription.id),
        before={"default_payment_method_id": before},
        after={"default_payment_method_id": payment_method},
        metadata={"setup_intent_id": setup_intent.get("id")},
    )


_EVENT_HANDLERS["setup_intent.succeeded"] = _handle_setup_intent_succeeded


def create_payment_setup_checkout(user):
    plan = Plan.objects.filter(code="free").first()
    if not plan:
        raise ValueError(
            "A free plan must be configured before saving a payment method."
        )
    subscription, _ = Subscription.objects.get_or_create(
        user=user, defaults={"plan": plan}
    )
    customer_id = get_or_create_stripe_customer(user, subscription)
    return _stripe().checkout.Session.create(
        mode="setup",
        customer=customer_id,
        payment_method_types=["card"],
        success_url=f"{settings.FRONTEND_BASE_URL}/billing/success",
        cancel_url=f"{settings.FRONTEND_BASE_URL}/billing/cancel",
        setup_intent_data={
            "metadata": {
                "user_id": str(user.pk),
                "purpose": "revenue_share_service_fee",
            }
        },
        client_reference_id=str(user.pk),
    )


def _handle_charge_refunded(charge):
    from billing.wallet import reverse_stripe_refund

    reverse_stripe_refund(charge)


_EVENT_HANDLERS["charge.refunded"] = _handle_charge_refunded
