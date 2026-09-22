import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.tests.factories import UserFactory
from virtual_numbers import services
from virtual_numbers.models import (
    IncomingSMS,
    NumberOffer,
    NumberOrder,
    PaymentEvent,
    PhoneNumber,
)
from virtual_numbers.serializers import AdminOfferSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(settings):
    settings.VIRTUAL_NUMBERS_ENABLED = True
    settings.VIRTUAL_NUMBERS_INGRESS_SECRET = "test-ingress-secret"
    settings.VIRTUAL_NUMBERS_STRIPE_WEBHOOK_SECRET = "whsec_numbers"
    settings.STAFF_2FA_REQUIRED = False
    offer = NumberOffer.objects.create(
        name="UK mobile",
        country_code="GB",
        country_name="UK",
        service="telegram",
        number_type="mobile",
        provider="contracted-test-provider",
        price_usd="5.00",
        base_cost_usd="5.00",
        sales_enabled=True,
        contract_confirmed=True,
        compatibility_confirmed=True,
    )
    phone = PhoneNumber.objects.create(
        offer=offer, number="+447700900123", provider_reference="test:number:1"
    )
    user = UserFactory()
    return user, offer, phone


def reserve(setup):
    user, offer, _ = setup
    with patch(
        "virtual_numbers.services.stripe.checkout.Session.create",
        return_value=SimpleNamespace(
            id="cs_number", url="https://checkout.stripe.com/test"
        ),
    ):
        return services.start_checkout(user, offer.pk, uuid.uuid4())


def event(order, event_id="evt_paid", **overrides):
    obj = dict(
        id="cs_number",
        metadata={"number_order_id": str(order.pk)},
        payment_status="paid",
        currency="usd",
        amount_total=650,
        mode="payment",
        client_reference_id=str(order.pk),
        payment_intent="pi_number",
    )
    obj.update(overrides)
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {"object": obj},
    }


def activate(setup):
    order = reserve(setup)
    services.process_payment(event(order))
    order.refresh_from_db()
    return order


def test_no_charge_before_launch(setup, settings):
    settings.VIRTUAL_NUMBERS_ENABLED = False
    with patch("virtual_numbers.services.stripe.checkout.Session.create") as create:
        with pytest.raises(ValidationError):
            services.start_checkout(setup[0], setup[1].pk, uuid.uuid4())
    create.assert_not_called()
    assert not NumberOrder.objects.exists()


def test_checkout_idempotence_and_inventory_exclusivity(setup):
    order = reserve(setup)
    again = services.start_checkout(setup[0], setup[1].pk, order.request_key)
    assert again.pk == order.pk
    with pytest.raises(ValidationError):
        services.start_checkout(UserFactory(), setup[1].pk, uuid.uuid4())
    assert NumberOrder.objects.count() == 1


def test_network_retry_keeps_same_reservation(setup):
    key = uuid.uuid4()
    with patch(
        "virtual_numbers.services.stripe.checkout.Session.create",
        side_effect=services.stripe.error.APIConnectionError("timeout"),
    ):
        with pytest.raises(services.stripe.error.APIConnectionError):
            services.start_checkout(setup[0], setup[1].pk, key)
    order = NumberOrder.objects.get()
    with patch(
        "virtual_numbers.services.stripe.checkout.Session.create",
        return_value=SimpleNamespace(
            id="cs_number", url="https://checkout.stripe.com/test"
        ),
    ) as create:
        retry = services.start_checkout(setup[0], setup[1].pk, key)
    assert retry.pk == order.pk
    assert create.call_args.kwargs["idempotency_key"] == f"number-order:{order.pk}"


def test_payment_is_verified_idempotent_and_retryable(setup):
    order = reserve(setup)
    with pytest.raises(ValidationError):
        services.process_payment(event(order, amount_total=1))
    assert not PaymentEvent.objects.exists()
    services.process_payment(event(order))
    order.refresh_from_db()
    expiry = order.expires_at
    services.process_payment(event(order))
    services.process_payment(event(order, event_id="evt_duplicate_payment"))
    order.refresh_from_db()
    assert order.status == "active" and order.expires_at == expiry
    assert order.phone.state == "assigned"


def test_expired_checkout_releases_only_unpaid_stock(setup):
    order = reserve(setup)
    expired = event(order)
    expired["type"] = "checkout.session.expired"
    services.process_payment(expired)
    order.refresh_from_db()
    assert order.status == "canceled"
    assert order.phone.state == "available"


def test_customer_cannot_read_other_inbox_and_sms_encrypted(setup):
    order = activate(setup)
    services.receive_sms(
        dict(
            provider_reference=order.phone.provider_reference,
            to=order.phone.number,
            event_id="sms-1",
            sender="Telegram",
            body="Private code 123456",
            received_at=timezone.now(),
        )
    )
    client = APIClient()
    client.force_authenticate(UserFactory())
    assert (
        client.get(f"/api/v1/virtual-numbers/orders/{order.pk}/messages").status_code
        == 404
    )
    client.force_authenticate(setup[0])
    response = client.get(f"/api/v1/virtual-numbers/orders/{order.pk}/messages")
    assert (
        response.status_code == 200
        and response.data[0]["body"] == "Private code 123456"
    )
    assert response["Cache-Control"] == "no-store, private"
    with connection.cursor() as cursor:
        cursor.execute("SELECT body_enc FROM virtual_numbers_incomingsms")
        assert b"123456" not in bytes(cursor.fetchone()[0])


def test_signed_sms_ingress_rejects_forgery_and_replay_is_noop(setup):
    order = activate(setup)
    client = APIClient()
    payload = json.dumps(
        dict(
            provider_reference=order.phone.provider_reference,
            to=order.phone.number,
            event_id="sms-1",
            sender="Telegram",
            body="123456",
            received_at=timezone.now().isoformat(),
        )
    )
    stamp = str(int(time.time()))
    signature = hmac.new(
        b"test-ingress-secret", stamp.encode() + b"." + payload.encode(), hashlib.sha256
    ).hexdigest()
    url = "/api/v1/webhooks/virtual-numbers/sms"
    assert client.post(url, payload, content_type="application/json").status_code == 403
    for _ in range(2):
        assert (
            client.post(
                url,
                payload,
                content_type="application/json",
                HTTP_X_SMS_TIMESTAMP=stamp,
                HTTP_X_SMS_SIGNATURE=signature,
            ).status_code
            == 200
        )
    assert IncomingSMS.objects.count() == 1
    assert (
        client.post(
            url,
            payload,
            content_type="application/json",
            HTTP_X_SMS_TIMESTAMP="1",
            HTTP_X_SMS_SIGNATURE=signature,
        ).status_code
        == 403
    )


def test_expiry_and_retention(setup):
    order = activate(setup)
    IncomingSMS.objects.create(
        order=order,
        event_id="old",
        sender_enc="Google",
        body_enc="secret",
        received_at=timezone.now() - timedelta(days=2),
        delete_after=timezone.now() - timedelta(hours=1),
    )
    order.expires_at = timezone.now() - timedelta(seconds=1)
    order.save()
    call_command("maintain_virtual_numbers")
    order.refresh_from_db()
    assert order.status == "expired" and order.phone.state == "retired"
    assert not IncomingSMS.objects.exists()


def test_refund_only_after_provider_confirmation(setup):
    order = activate(setup)
    services.request_refund(order.pk, setup[0], "SMS not received")
    with patch(
        "virtual_numbers.services.stripe.Refund.create",
        return_value=SimpleNamespace(status="pending"),
    ):
        with pytest.raises(ValidationError):
            services.refund_order(order.pk, setup[0])
    order.refresh_from_db()
    assert order.status == "refund_requested"
    with patch(
        "virtual_numbers.services.stripe.Refund.create",
        return_value=SimpleNamespace(status="succeeded"),
    ) as create:
        services.refund_order(order.pk, setup[0])
        services.refund_order(order.pk, setup[0])
    assert create.call_count == 1
    order.refresh_from_db()
    assert order.status == "refunded" and order.phone.state == "retired"


def test_admin_access_and_unsupported_offer(setup):
    client = APIClient()
    client.force_authenticate(setup[0])
    assert client.get("/api/v1/admin/virtual-numbers/offers").status_code == 403
    serializer = AdminOfferSerializer(
        instance=setup[1], data={"number_type": "voip"}, partial=True
    )
    assert not serializer.is_valid()
    setup[0].is_superuser = True
    setup[0].save()
    assert client.get("/api/v1/admin/virtual-numbers/offers").status_code == 200


def test_stripe_invalid_signature_cannot_activate(setup):
    order = reserve(setup)
    response = APIClient().post(
        "/api/v1/webhooks/virtual-numbers/stripe", event(order), format="json"
    )
    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == "pending"


def test_dashboard_refund_revokes_inbox(setup):
    order = activate(setup)
    services.process_payment(
        {
            "id": "evt_refund",
            "type": "charge.refunded",
            "data": {
                "object": {
                    "payment_intent": "pi_number",
                    "refunded": True,
                    "amount_refunded": 650,
                }
            },
        }
    )
    order.refresh_from_db()
    assert order.status == "refunded" and order.phone.state == "retired"


def test_early_or_wrong_recipient_sms_is_discarded(setup):
    order = activate(setup)
    data = dict(
        provider_reference=order.phone.provider_reference,
        to=order.phone.number,
        event_id="wrong",
        sender="Telegram",
        body="secret",
        received_at=order.activated_at - timedelta(seconds=1),
    )
    services.receive_sms(data)
    services.receive_sms({**data, "received_at": timezone.now(), "to": "+447700900999"})
    assert not IncomingSMS.objects.exists()


def test_signed_payment_endpoint_activates_order(setup):
    order = reserve(setup)
    payload = json.dumps({**event(order), "object": "event"})
    stamp = str(int(time.time()))
    signature = hmac.new(
        b"whsec_numbers", (stamp + "." + payload).encode(), hashlib.sha256
    ).hexdigest()
    response = APIClient().post(
        "/api/v1/webhooks/virtual-numbers/stripe",
        payload,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=f"t={stamp},v1={signature}",
    )
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.status == "active"


@pytest.mark.django_db(transaction=True)
def test_simultaneous_customers_cannot_buy_same_number(setup):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    users = [setup[0], UserFactory()]

    def buy(user):
        close_old_connections()
        try:
            return services.start_checkout(user, setup[1].pk, uuid.uuid4()).pk
        except ValidationError:
            return None
        finally:
            close_old_connections()

    with patch(
        "virtual_numbers.services.stripe.checkout.Session.create",
        return_value=SimpleNamespace(
            id="cs_number", url="https://checkout.stripe.com/test"
        ),
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(buy, users))
    assert sum(r is not None for r in results) == 1
    assert NumberOrder.objects.count() == 1
