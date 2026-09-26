"""Website-service orders: contract acceptance, Payoneer checkout, fulfilment."""

import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from audit.services import record_audit_event
from payoneer import client
from payoneer.services import default_checkout_account
from web_services import contract
from web_services.models import ExecutorProfile, OrderStatus, ServiceOrder

MAX_PENDING = 3
PAYONEER_LANGUAGES = {"uz": "uz_UZ", "ru": "ru_RU", "en": "en_US"}


def audit(action, order, actor=None):
    record_audit_event(
        actor_type="user" if actor else "system",
        actor_id=actor.pk if actor else None,
        action=f"web_services.{action}",
        resource_type="ServiceOrder",
        resource_id=str(order.pk),
    )


def sales_state():
    executor = ExecutorProfile.load()
    if not executor.sales_enabled:
        return False, "sales_paused"
    if not executor.complete:
        return False, "executor_details_required"
    if not default_checkout_account():
        return False, "payment_account_required"
    return True, ""


def draft_document(data, executor=None, *, number="", date=""):
    package = data["package"]
    return contract.build(
        kind=data["contract_type"],
        executor=(executor or ExecutorProfile.load()).snapshot(),
        customer=data["customer"],
        package=package.terms(),
        price=package.price_usd,
        project=data["project"],
        number=number,
        date=date,
    )


def _next_number(year):
    prefix = f"WS-{year}-"
    count = ServiceOrder.objects.filter(number__startswith=prefix).count()
    return f"{prefix}{count + 1:05d}"


def create_order(user, data, *, ip=None, user_agent=""):
    ready, reason = sales_state()
    if not ready:
        raise ValidationError({"detail": "Orders are not being accepted yet.", "code": reason})
    package = data["package"]
    with transaction.atomic():
        # The executor row doubles as the lock that keeps contract numbers gapless.
        executor = ExecutorProfile.objects.select_for_update().get(pk=1)
        type(user).objects.select_for_update().get(pk=user.pk)
        existing = ServiceOrder.objects.filter(user=user, request_key=data["request_key"]).first()
        if existing:
            if existing.package_id != package.pk:
                raise ValidationError("This request key belongs to another order.")
            order = existing
        else:
            if Decimal(data["quoted_total"]) != package.price_usd:
                raise ValidationError("The price changed. Review the package before paying.")
            if contract.checksum(draft_document(data, executor)) != data["preview_checksum"]:
                raise ValidationError(
                    "The contract terms changed since you opened them. Review the contract again."
                )
            if (
                ServiceOrder.objects.filter(user=user, status=OrderStatus.PENDING_PAYMENT).count()
                >= MAX_PENDING
            ):
                raise ValidationError("Complete or cancel your unpaid orders first.")
            now = timezone.localtime()
            number = _next_number(now.year)
            document = draft_document(data, executor, number=number, date=now.date().isoformat())
            order = ServiceOrder.objects.create(
                number=number,
                user=user,
                package=package,
                request_key=data["request_key"],
                price_usd=package.price_usd,
                contract_type=data["contract_type"],
                project_name=data["project"]["name"],
                contract_enc=json.dumps(document, ensure_ascii=False),
                contract_version=contract.CONTRACT_VERSION,
                contract_sha256=contract.checksum(document),
                accepted_at=timezone.now(),
                accepted_ip=ip,
                accepted_user_agent=user_agent[:300],
                account=default_checkout_account(),
            )
            audit("contract_accepted", order, user)
    if order.status == OrderStatus.PENDING_PAYMENT and not order.checkout_url:
        order = open_checkout(order, language=getattr(user, "locale", "en"))
    return order


def open_checkout(order, language="en"):
    """Create (or recreate) the hosted Payoneer page for an unpaid order."""
    account = order.account or default_checkout_account()
    if not account or not account.checkout_ready:
        raise ValidationError("No Payoneer account is available for checkout.")
    customer = order.contract["customer"]
    first, _, last = customer["full_name"].partition(" ")
    long_id, url = client.create_session(
        account,
        transaction_id=order.number,
        amount=order.price_usd,
        currency=order.currency,
        reference=f"Website {order.number}",
        product={"code": order.package.code, "name": order.contract["package_name"]},
        customer={
            "number": str(order.user_id),
            "email": customer["email"],
            "first_name": first,
            "last_name": last or first,
            "street": customer["address"],
            "city": customer["city"],
            "country": customer["country_code"],
        },
        callback={
            "returnUrl": f"{settings.FRONTEND_BASE_URL}/web-services?order={order.pk}&payment=return",
            "cancelUrl": f"{settings.FRONTEND_BASE_URL}/web-services?order={order.pk}&payment=canceled",
            "notificationUrl": (
                f"{settings.BACKEND_BASE_URL.rstrip('/')}/api/v1/webhooks/payoneer/{account.pk}/checkout"
            ),
        },
        language=PAYONEER_LANGUAGES.get(language, "en_US"),
    )
    with transaction.atomic():
        order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
        order.account, order.checkout_id, order.checkout_url = account, long_id, url
        order.save(update_fields=["account", "checkout_id", "checkout_url", "updated_at"])
    return order


def resume_checkout(order, language="en"):
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise ValidationError("This order is not awaiting payment.")
    if order.checkout_id:
        session = client.get_session(order.account, order.checkout_id) or {}
        code = session.get("status", {}).get("code", "")
        if code in client.PAID_STATUSES:
            return confirm_payment(order.pk)
        if code in ("listed", "pending", "preauthorized"):
            return order
    return open_checkout(order, language)


def _matches(order, data):
    payment = data.get("payment") or {}
    try:
        amount_ok = Decimal(str(payment.get("amount"))).quantize(Decimal("0.01")) == order.price_usd
    except (InvalidOperation, TypeError):
        amount_ok = False
    reference = (data.get("identification") or {}).get("transactionId")
    return amount_ok and payment.get("currency") == order.currency and reference == order.number


def confirm_payment(order_id, charge_id=""):
    """Ask Payoneer for the truth; a browser return alone never marks payment."""
    order = ServiceOrder.objects.select_related("account").get(pk=order_id)
    if order.status != OrderStatus.PENDING_PAYMENT and not charge_id:
        return order
    if charge_id:
        data = client.get_charge(order.account, charge_id)
    elif order.checkout_id:
        data = client.get_session(order.account, order.checkout_id)
    else:
        return order
    code = (data or {}).get("status", {}).get("code")
    if code not in client.PAID_STATUSES and code != client.REFUNDED_STATUS:
        return order
    if not _matches(order, data):
        raise ValidationError("Payoneer amount or reference does not match this order.")
    with transaction.atomic():
        order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
        fields = ["updated_at"]
        if code == client.REFUNDED_STATUS:
            if order.status in REFUNDABLE:
                order.status = OrderStatus.REFUNDED
                order.save(update_fields=["status", "updated_at"])
                audit("refunded", order)
            return order
        if charge_id and not order.charge_id:
            order.charge_id = charge_id
            fields.append("charge_id")
        if order.status in (OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELED):
            order.status, order.paid_at = OrderStatus.PAID, timezone.now()
            fields += ["status", "paid_at"]
            audit("paid", order)
        order.save(update_fields=fields)
    return order


def handle_notification(account, params):
    order = ServiceOrder.objects.filter(
        account=account, number=params.get("transactionId", "")
    ).first()
    if not order:
        return None
    long_id = params.get("longId", "")
    if params.get("entity") == "payment" and long_id and len(long_id) <= 120:
        return confirm_payment(order.pk, charge_id=long_id)
    return confirm_payment(order.pk)


REFUNDABLE = {
    OrderStatus.PAID,
    OrderStatus.IN_PROGRESS,
    OrderStatus.DELIVERED,
    OrderStatus.REFUND_PENDING,
}

ADMIN_TRANSITIONS = {
    OrderStatus.PENDING_PAYMENT: {OrderStatus.CANCELED},
    OrderStatus.PAID: {OrderStatus.IN_PROGRESS, OrderStatus.CANCELED},
    OrderStatus.IN_PROGRESS: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: {OrderStatus.IN_PROGRESS},
}


def update_status(order_id, status, note, actor):
    with transaction.atomic():
        order = ServiceOrder.objects.select_for_update().get(pk=order_id)
        if status != order.status and status not in ADMIN_TRANSITIONS.get(order.status, set()):
            raise ValidationError(f"An order cannot move from {order.status} to {status}.")
        if order.status == OrderStatus.PAID and status == OrderStatus.CANCELED:
            raise ValidationError("A paid order is canceled by refunding it.")
        order.status = status
        if note is not None:
            order.admin_note = note
        order.save(update_fields=["status", "admin_note", "updated_at"])
        audit(f"status_{status}", order, actor)
    if status == OrderStatus.CANCELED and order.checkout_id:
        try:
            client.checkout_request(order.account, "DELETE", f"/lists/{order.checkout_id}")
        except APIException:
            pass  # An abandoned session simply expires at Payoneer.
    return order


def refund(order_id, actor):
    order = ServiceOrder.objects.select_related("account").get(pk=order_id)
    if order.status == OrderStatus.REFUNDED:
        return order
    if order.status not in REFUNDABLE:
        raise ValidationError("Only a paid order can be refunded.")
    if not order.charge_id:
        raise ValidationError(
            "Payoneer has not reported the charge for this order yet; refund it from the Payoneer portal."
        )
    result = client.refund_charge(
        order.account,
        order.charge_id,
        transaction_id=order.number,
        amount=order.price_usd,
        currency=order.currency,
        reference=f"Refund {order.number}",
    ) or {}
    code = result.get("status", {}).get("code", "")
    if code == "paid_out":
        status = OrderStatus.REFUNDED
    elif code in ("pending", "payout_requested"):
        status = OrderStatus.REFUND_PENDING
    else:
        raise ValidationError(f"Payoneer did not accept the refund ({code or 'no status'}).")
    with transaction.atomic():
        order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
        order.status = status
        order.save(update_fields=["status", "updated_at"])
        audit(status, order, actor)
    return order
