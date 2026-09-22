"""Dedicated number rentals. Provider connectors must implement the signed ingress contract."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from audit.services import record_audit_event
from virtual_numbers.gateways import (
    payment_methods,
    paypal,
    require_gateway,
    stripe_key,
)
from virtual_numbers.models import (
    IncomingSMS,
    NumberOffer,
    NumberOrder,
    PaymentEvent,
    PhoneNumber,
)
from virtual_numbers.pricing import quote

TERMS_VERSION = "2026-09-22"


def integration_ready():
    return bool(
        settings.VIRTUAL_NUMBERS_ENABLED
        and settings.VIRTUAL_NUMBERS_INGRESS_SECRET
        and any(method["available"] for method in payment_methods())
    )


def unavailable_reason(offer):
    if offer.base_cost_usd is None:
        return "pricing_required"
    if not integration_ready():
        return "integration_pending"
    if not (
        offer.is_visible
        and offer.sales_enabled
        and offer.contract_confirmed
        and offer.compatibility_confirmed
    ):
        return "approval_pending"
    if offer.service in ("telegram", "whatsapp") and offer.number_type != "mobile":
        return "incompatible_number_type"
    if not offer.numbers.filter(state="available").exists():
        return "out_of_stock"
    return ""


def audit(action, obj, actor=None):
    record_audit_event(
        actor_type="user" if actor else "system",
        actor_id=actor.pk if actor else None,
        action=f"virtual_numbers.{action}",
        resource_type=obj.__class__.__name__,
        resource_id=str(obj.pk),
    )


def start_checkout(
    user, offer_id, request_key, payment_provider="stripe", quoted_total=None
):
    require_gateway(payment_provider)
    # Serialize purchases by user; commit the reservation before any remote side effect.
    with transaction.atomic():
        type(user).objects.select_for_update().get(pk=user.pk)
        order = (
            NumberOrder.objects.select_for_update()
            .filter(user=user, request_key=request_key)
            .first()
        )
        if order:
            if (
                str(order.offer_id) != str(offer_id)
                or order.payment_provider != payment_provider
            ):
                raise ValidationError("This request key belongs to another offer.")
            if order.status != "pending":
                raise ValidationError("This order is no longer awaiting payment.")
            if order.checkout_id:
                return order
        else:
            offer = NumberOffer.objects.select_for_update().filter(pk=offer_id).first()
            if not offer or unavailable_reason(offer):
                raise ValidationError("This offer is not available for purchase yet.")
            breakdown = quote(offer.base_cost_usd, offer.tax_basis)
            if quoted_total is not None and Decimal(quoted_total) != Decimal(
                breakdown["total"]
            ):
                raise ValidationError(
                    "The price changed. Refresh the catalog before paying."
                )
            if NumberOrder.objects.filter(user=user, status="pending").count() >= 3:
                raise ValidationError(
                    "Complete or wait for your pending checkouts to expire first."
                )
            phone = (
                offer.numbers.select_for_update(skip_locked=True)
                .filter(state="available")
                .first()
            )
            if not phone:
                raise ValidationError("No numbers are currently available.")
            phone.state = "reserved"
            phone.save(update_fields=["state", "updated_at"])
            order = NumberOrder.objects.create(
                user=user,
                offer=offer,
                phone=phone,
                request_key=request_key,
                offer_name=offer.name,
                service=offer.service,
                price_usd=Decimal(breakdown["total"]),
                price_breakdown=breakdown,
                payment_provider=payment_provider,
                rental_days=offer.rental_days,
                terms_version=TERMS_VERSION,
            )
            audit("reserved", order, user)
    if not integration_ready():
        raise ValidationError("Number sales are temporarily paused.")
    # Retry with the same key after network timeouts: never make a second charge/session.
    if timezone.now() >= order.created_at + timedelta(minutes=25):
        raise ValidationError(
            "Checkout creation window elapsed. Contact support to reconcile this reservation."
        )
    if order.payment_provider == "paypal":
        checkout_id, checkout_url = paypal.create_checkout(order)
    else:
        session = stripe.checkout.Session.create(
            api_key=stripe_key(),
            idempotency_key=f"number-order:{order.pk}",
            mode="payment",
            payment_method_types=["card"],
            client_reference_id=str(order.pk),
            metadata={"number_order_id": str(order.pk)},
            payment_intent_data={"metadata": {"number_order_id": str(order.pk)}},
            line_items=stripe_line_items(order),
            expires_at=int((order.created_at + timedelta(hours=1)).timestamp()),
            success_url=f"{settings.FRONTEND_BASE_URL}/virtual-numbers?payment=received",
            cancel_url=f"{settings.FRONTEND_BASE_URL}/virtual-numbers?payment=canceled",
        )
        checkout_id, checkout_url = session.id, session.url
    with transaction.atomic():
        order = NumberOrder.objects.select_for_update().get(pk=order.pk)
        order.checkout_id, order.checkout_url = checkout_id, checkout_url
        order.save(update_fields=["checkout_id", "checkout_url", "updated_at"])
    return order


@transaction.atomic
def process_payment(event):
    # Event receipt and state transition commit together, so failed handlers remain retryable.
    _, created = PaymentEvent.objects.get_or_create(event_id=event["id"])
    if not created:
        return
    obj = event["data"]["object"]
    if event["type"] == "charge.refunded":
        order = (
            NumberOrder.objects.select_for_update()
            .filter(
                payment_provider="stripe", payment_intent=obj.get("payment_intent", "")
            )
            .exclude(payment_intent="")
            .first()
        )
        if (
            order
            and obj.get("refunded")
            and obj.get("amount_refunded", 0) >= int(order.price_usd * 100)
        ):
            order.status = "refunded"
            order.save(update_fields=["status", "updated_at"])
            PhoneNumber.objects.filter(pk=order.phone_id).update(state="retired")
            order.messages.all().delete()
            audit("refunded", order)
        return
    order_id = obj.get("metadata", {}).get("number_order_id")
    if not order_id:
        return
    order = NumberOrder.objects.select_for_update().filter(pk=order_id).first()
    if not order or order.payment_provider != "stripe":
        raise ValidationError("Unknown Stripe number order.")
    kind = event["type"]
    if kind not in ("checkout.session.completed", "checkout.session.expired"):
        return
    if order.checkout_id and order.checkout_id != obj["id"]:
        raise ValidationError("Checkout does not match this order.")
    phone = PhoneNumber.objects.select_for_update().get(pk=order.phone_id)
    if kind == "checkout.session.expired" and order.status == "pending":
        order.status = "canceled"
        phone.state = "available"
    elif kind == "checkout.session.completed":
        if obj.get("payment_status") != "paid":
            return
        if (
            obj.get("currency") != "usd"
            or obj.get("amount_total") != int(order.price_usd * 100)
            or obj.get("mode") != "payment"
            or obj.get("client_reference_id") != str(order.pk)
        ):
            raise ValidationError("Payment amount or reference does not match.")
        if order.status != "pending":
            return
        if phone.state != "reserved":
            raise ValidationError(
                "Reserved number unavailable; manual reconciliation required."
            )
        order.status = "active"
        order.activated_at = timezone.now()
        order.expires_at = order.activated_at + timedelta(days=order.rental_days)
        order.payment_intent = obj["payment_intent"]
        order.checkout_id = obj["id"]
        phone.state = "assigned"
    else:
        return
    order.save()
    phone.save(update_fields=["state", "updated_at"])
    audit(order.status, order)


@transaction.atomic
def receive_sms(data):
    phone = (
        PhoneNumber.objects.select_for_update()
        .filter(
            provider_reference=data["provider_reference"],
            number=data["to"],
            state="assigned",
        )
        .first()
    )
    if not phone:
        return
    order = NumberOrder.objects.filter(
        phone=phone,
        status__in=["active", "refund_requested"],
        activated_at__lte=data["received_at"],
        expires_at__gt=timezone.now(),
    ).first()
    if (
        not order
        or data["received_at"] > timezone.now() + timedelta(minutes=5)
        or data["received_at"] < timezone.now() - timedelta(hours=24)
    ):
        return
    IncomingSMS.objects.get_or_create(
        event_id=data["event_id"],
        defaults={
            "order": order,
            "sender_enc": data["sender"],
            "body_enc": data["body"],
            "received_at": data["received_at"],
            "delete_after": min(order.expires_at, timezone.now() + timedelta(hours=24)),
        },
    )


@transaction.atomic
def request_refund(order_id, user, reason):
    order = NumberOrder.objects.select_for_update().get(pk=order_id, user=user)
    if order.status == "refund_requested":
        return order
    if order.status not in ("active", "expired"):
        raise ValidationError("This order cannot be submitted for refund review.")
    order.status, order.refund_reason = "refund_requested", reason
    order.save(update_fields=["status", "refund_reason", "updated_at"])
    audit("refund_requested", order, user)
    return order


def refund_order(order_id, actor):
    order = NumberOrder.objects.get(pk=order_id)
    if order.status == "refunded":
        return order
    if order.status != "refund_requested" or not order.payment_intent:
        raise ValidationError("A paid refund request is required.")
    if order.payment_provider == "paypal":
        result = paypal.refund(order)
        if result.get("status") != "COMPLETED":
            raise ValidationError(
                "PayPal refund is pending. Retry reconciliation later."
            )
        amount = result.get("amount", {})
        if (
            amount.get("currency_code") != "USD"
            or Decimal(amount.get("value", "-1")) != order.price_usd
        ):
            raise ValidationError("PayPal refund amount did not match the order.")
    else:
        result = stripe.Refund.create(
            api_key=stripe_key(),
            payment_intent=order.payment_intent,
            amount=int(order.price_usd * Decimal(100)),
            idempotency_key=f"number-refund:{order.pk}",
        )
        if result.status != "succeeded":
            raise ValidationError(
                "Refund is pending at Stripe. Retry reconciliation later."
            )
    with transaction.atomic():
        order = NumberOrder.objects.select_for_update().get(pk=order.pk)
        order.status = "refunded"
        order.save(update_fields=["status", "updated_at"])
        PhoneNumber.objects.filter(pk=order.phone_id).update(state="retired")
        order.messages.all().delete()
        audit("refunded", order, actor)
    return order


def stripe_line_items(order):
    amounts = [(f"{order.offer_name} ({order.rental_days} days)", str(order.price_usd))]
    if order.price_breakdown:
        p = order.price_breakdown
        amounts = [
            (f"{order.offer_name} — provider cost", p["base_cost"]),
            ("Platform fee (18%)", p["profit"]),
            ("Tax (12%)", p["tax"]),
        ]
    return [
        {
            "price_data": {
                "currency": "usd",
                "unit_amount": int(Decimal(amount) * 100),
                "product_data": {"name": name},
            },
            "quantity": 1,
        }
        for name, amount in amounts
        if Decimal(amount) > 0
    ]


def validate_paypal_order(order, data):
    units = data.get("purchase_units", [])
    if data.get("id") != order.checkout_id or len(units) != 1:
        raise ValidationError("PayPal order reference does not match.")
    unit = units[0]
    amount = unit.get("amount", {})
    try:
        valid_amount = Decimal(amount.get("value", "-1")) == order.price_usd
    except InvalidOperation:
        valid_amount = False
    if (
        unit.get("custom_id") != str(order.pk)
        or unit.get("reference_id") != str(order.pk)
        or unit.get("payee", {}).get("merchant_id") != settings.PAYPAL_MERCHANT_ID
        or amount.get("currency_code") != "USD"
        or not valid_amount
    ):
        raise ValidationError("PayPal amount, currency or merchant does not match.")
    return unit


@transaction.atomic
def complete_paypal_order(order_id, user=None):
    query = NumberOrder.objects.select_for_update().filter(
        pk=order_id, payment_provider="paypal"
    )
    if user is not None:
        query = query.filter(user=user)
    order = query.first()
    if not order or not order.checkout_id:
        raise ValidationError("Unknown PayPal number order.")
    if order.status != "pending":
        return order
    data = paypal.get_order(order.checkout_id)
    unit = validate_paypal_order(order, data)
    if data.get("status") == "APPROVED":
        paypal.capture(order)
        data = paypal.get_order(order.checkout_id)
        unit = validate_paypal_order(order, data)
    if data.get("status") != "COMPLETED":
        # Approval, a browser return, or a pending capture never activates service.
        return order
    captures = unit.get("payments", {}).get("captures", [])
    if len(captures) != 1:
        raise ValidationError("Unexpected PayPal capture count.")
    capture = captures[0]
    if capture.get("status") != "COMPLETED":
        return order
    amount = capture.get("amount", {})
    if (
        not capture.get("id")
        or amount.get("currency_code") != "USD"
        or Decimal(amount.get("value", "-1")) != order.price_usd
    ):
        raise ValidationError("Captured PayPal amount does not match.")
    phone = PhoneNumber.objects.select_for_update().get(pk=order.phone_id)
    if phone.state != "reserved":
        raise ValidationError(
            "Reserved number unavailable. Payment requires reconciliation."
        )
    order.payment_intent = capture["id"]
    order.status = "active"
    order.activated_at = timezone.now()
    order.expires_at = order.activated_at + timedelta(days=order.rental_days)
    order.save()
    phone.state = "assigned"
    phone.save(update_fields=["state", "updated_at"])
    audit("active", order)
    return order


@transaction.atomic
def process_paypal_event(event):
    event_id = event.get("id", "")
    if not isinstance(event_id, str) or not event_id or len(event_id) > 200:
        raise ValidationError("Invalid PayPal event ID.")
    _, created = PaymentEvent.objects.get_or_create(event_id=f"paypal:{event_id}")
    if not created:
        return
    resource = event.get("resource", {})
    kind = event.get("event_type")
    if kind in ("CHECKOUT.ORDER.APPROVED", "PAYMENT.CAPTURE.COMPLETED"):
        checkout_id = (
            resource.get("id")
            if kind == "CHECKOUT.ORDER.APPROVED"
            else resource.get("supplementary_data", {})
            .get("related_ids", {})
            .get("order_id")
        )
        order = NumberOrder.objects.filter(
            payment_provider="paypal", checkout_id=checkout_id
        ).first()
        if not order:
            # Ignore other products' events, but retry known local orders whose
            # remote ID was not committed yet after a create-checkout timeout.
            if (
                resource.get("custom_id")
                and NumberOrder.objects.filter(
                    pk=resource["custom_id"], payment_provider="paypal"
                ).exists()
            ):
                raise ValidationError("PayPal checkout is still being reconciled.")
            return
        complete_paypal_order(order.pk)
    elif kind == "PAYMENT.CAPTURE.REFUNDED":
        capture_id = (
            resource.get("supplementary_data", {})
            .get("related_ids", {})
            .get("capture_id")
        )
        # PayPal's refund resource also supplies a standard 'up' capture link.
        if not capture_id:
            from urllib.parse import urlparse

            for link in resource.get("links", []):
                parsed = urlparse(link.get("href", ""))
                if link.get("rel") == "up" and parsed.path.startswith(
                    "/v2/payments/captures/"
                ):
                    capture_id = parsed.path.rsplit("/", 1)[-1]
        if not capture_id:
            raise ValidationError("Missing PayPal capture reference.")
        order = (
            NumberOrder.objects.select_for_update()
            .filter(payment_provider="paypal", payment_intent=capture_id)
            .first()
        )
        if not order:
            raise ValidationError("Capture must be reconciled before its refund.")
        capture = paypal.get_capture(capture_id)
        if capture.get("id") != capture_id:
            raise ValidationError("PayPal capture reference does not match.")
        if capture.get("status") != "REFUNDED":
            return  # Partial refunds do not revoke the entire rental.
        order.status = "refunded"
        order.save(update_fields=["status", "updated_at"])
        PhoneNumber.objects.filter(pk=order.phone_id).update(state="retired")
        order.messages.all().delete()
        audit("refunded", order)
