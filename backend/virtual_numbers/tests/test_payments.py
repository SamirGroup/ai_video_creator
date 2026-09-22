import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.tests.factories import UserFactory
from virtual_numbers import services
from virtual_numbers.gateways import GatewayUnavailable, payment_methods, paypal
from virtual_numbers.models import NumberOffer, NumberOrder, PaymentEvent, PhoneNumber
from virtual_numbers.pricing import quote

pytestmark = pytest.mark.django_db


@pytest.fixture
def rental(settings):
    settings.VIRTUAL_NUMBERS_ENABLED = True
    settings.VIRTUAL_NUMBERS_INGRESS_SECRET = "test-sms"
    settings.PAYPAL_ENABLED = True
    settings.PAYPAL_MODE = "sandbox"
    settings.PAYPAL_CLIENT_ID = "test-id"
    settings.PAYPAL_CLIENT_SECRET = "test-secret"
    settings.PAYPAL_MERCHANT_ID = "merchant123"
    settings.PAYPAL_WEBHOOK_ID = "webhook123"
    settings.STAFF_2FA_REQUIRED = False
    offer = NumberOffer.objects.create(
        name="Test mobile",
        country_code="GB",
        country_name="UK",
        service="telegram",
        number_type="mobile",
        provider="test",
        base_cost_usd=Decimal("100.00"),
        sales_enabled=True,
        contract_confirmed=True,
        compatibility_confirmed=True,
    )
    PhoneNumber.objects.create(
        offer=offer, number="+447700900111", provider_reference="test:1"
    )
    return UserFactory(), offer


def reserve(rental):
    user, offer = rental
    with patch.object(
        paypal,
        "create_checkout",
        return_value=(
            "PPORDER123",
            "https://www.sandbox.paypal.com/checkoutnow?token=PPORDER123",
        ),
    ):
        return services.start_checkout(user, offer.pk, uuid.uuid4(), "paypal", "130.00")


def remote_order(order, status="COMPLETED", capture_status="COMPLETED"):
    return {
        "id": order.checkout_id,
        "status": status,
        "purchase_units": [
            {
                "reference_id": str(order.pk),
                "custom_id": str(order.pk),
                "payee": {"merchant_id": "merchant123"},
                "amount": {"value": "130.00", "currency_code": "USD"},
                "payments": {
                    "captures": [
                        {
                            "id": "CAPTURE123",
                            "status": capture_status,
                            "amount": {"value": "130.00", "currency_code": "USD"},
                        }
                    ]
                },
            }
        ],
    }


def test_pricing_rounding_and_tax_base():
    p = quote("100")
    assert (p["profit"], p["tax"], p["total"]) == ("18.00", "12.00", "130.00")
    assert quote("100", "subtotal")["total"] == "132.16"
    for cost in ("1.01", "3.33", "10.05", "1234.56"):
        p = quote(cost)
        assert Decimal(p["base_cost"]) + Decimal(p["profit"]) + Decimal(
            p["tax"]
        ) == Decimal(p["total"])


def test_snapshot_and_client_price_tampering(rental):
    with pytest.raises(ValidationError):
        services.start_checkout(rental[0], rental[1].pk, uuid.uuid4(), "paypal", "1.00")
    assert not NumberOrder.objects.exists()
    order = reserve(rental)
    rental[1].base_cost_usd = Decimal(200)
    rental[1].save()
    order.refresh_from_db()
    assert order.price_usd == Decimal(130)
    assert order.price_breakdown["base_cost"] == "100.00"
    lines = services.stripe_line_items(order)
    assert sum(line["price_data"]["unit_amount"] for line in lines) == 13000


def test_allpay_fails_closed_before_reserving_stock(rental):
    with pytest.raises(GatewayUnavailable):
        services.start_checkout(
            rental[0], rental[1].pk, uuid.uuid4(), "allpay", "130.00"
        )
    assert not NumberOrder.objects.exists()
    assert PhoneNumber.objects.get().state == "available"
    assert not next(m for m in payment_methods() if m["code"] == "allpay")["available"]


def test_checkout_uses_paypal_not_stripe(rental):
    order = reserve(rental)
    assert order.payment_provider == "paypal" and order.price_usd == Decimal("130.00")
    with patch.object(
        paypal,
        "request",
        return_value={
            "id": "PPORDER123",
            "links": [
                {
                    "rel": "payer-action",
                    "href": "https://www.sandbox.paypal.com/checkoutnow?token=PPORDER123",
                }
            ],
        },
    ) as req:
        paypal.create_checkout(order)
    payload = req.call_args.kwargs["payload"]
    unit = payload["purchase_units"][0]
    assert unit["amount"]["value"] == "130.00"
    assert unit["amount"]["breakdown"]["tax_total"]["value"] == "12.00"
    assert unit["payee"]["merchant_id"] == "merchant123"


def test_approval_and_pending_capture_do_not_fulfill(rental):
    order = reserve(rental)
    with (
        patch.object(
            paypal,
            "get_order",
            side_effect=[
                remote_order(order, "APPROVED"),
                remote_order(order, "COMPLETED", "PENDING"),
            ],
        ),
        patch.object(paypal, "capture") as capture,
    ):
        services.complete_paypal_order(order.pk, rental[0])
    order.refresh_from_db()
    assert order.status == "pending"
    capture.assert_called_once()
    with patch.object(paypal, "get_order", return_value=remote_order(order)):
        services.complete_paypal_order(order.pk, rental[0])
        services.complete_paypal_order(order.pk, rental[0])
    order.refresh_from_db()
    assert order.status == "active" and order.payment_intent == "CAPTURE123"


@pytest.mark.parametrize(
    "field,value",
    [
        ("merchant", "wrong"),
        ("amount", "1.00"),
        ("currency", "GBP"),
        ("reference", "wrong"),
    ],
)
def test_paypal_payment_identity_validation(rental, field, value):
    order = reserve(rental)
    data = remote_order(order)
    unit = data["purchase_units"][0]
    if field == "merchant":
        unit["payee"]["merchant_id"] = value
    if field == "amount":
        unit["amount"]["value"] = value
    if field == "currency":
        unit["amount"]["currency_code"] = value
    if field == "reference":
        unit["custom_id"] = value
    with (
        patch.object(paypal, "get_order", return_value=data),
        pytest.raises(ValidationError),
    ):
        services.complete_paypal_order(order.pk, rental[0])
    order.refresh_from_db()
    assert order.status == "pending"


def test_webhook_requires_verification_and_retries_failed_processing(rental):
    order = reserve(rental)
    event = {
        "id": "WH123",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "CAPTURE123",
            "supplementary_data": {"related_ids": {"order_id": order.checkout_id}},
        },
    }
    client = APIClient()
    assert (
        client.post(
            "/api/v1/webhooks/virtual-numbers/paypal", event, format="json"
        ).status_code
        == 403
    )
    bad = remote_order(order)
    bad["purchase_units"][0]["amount"]["value"] = "1.00"
    with (
        patch.object(paypal, "verify_webhook", return_value=True),
        patch.object(paypal, "get_order", return_value=bad),
    ):
        assert (
            client.post(
                "/api/v1/webhooks/virtual-numbers/paypal", event, format="json"
            ).status_code
            == 400
        )
    assert not PaymentEvent.objects.filter(event_id="paypal:WH123").exists()
    with (
        patch.object(paypal, "verify_webhook", return_value=True),
        patch.object(paypal, "get_order", return_value=remote_order(order)),
    ):
        assert (
            client.post(
                "/api/v1/webhooks/virtual-numbers/paypal", event, format="json"
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/webhooks/virtual-numbers/paypal", event, format="json"
            ).status_code
            == 200
        )
    order.refresh_from_db()
    assert order.status == "active"


def test_capture_is_owner_only(rental):
    order = reserve(rental)
    client = APIClient()
    client.force_authenticate(UserFactory())
    with patch.object(paypal, "capture") as capture:
        assert (
            client.post(
                f"/api/v1/virtual-numbers/orders/{order.pk}/paypal-capture"
            ).status_code
            == 404
        )
    capture.assert_not_called()


def test_paypal_refund_and_partial_refund_behavior(rental):
    order = reserve(rental)
    with patch.object(paypal, "get_order", return_value=remote_order(order)):
        services.complete_paypal_order(order.pk)
    event = {
        "id": "WHREF1",
        "event_type": "PAYMENT.CAPTURE.REFUNDED",
        "resource": {
            "links": [
                {
                    "rel": "up",
                    "href": "https://api-m.sandbox.paypal.com/v2/payments/captures/CAPTURE123",
                }
            ]
        },
    }
    with patch.object(
        paypal,
        "get_capture",
        return_value={"id": "CAPTURE123", "status": "PARTIALLY_REFUNDED"},
    ):
        services.process_paypal_event(event)
    order.refresh_from_db()
    assert order.status == "active"
    event["id"] = "WHREF2"
    with patch.object(
        paypal, "get_capture", return_value={"id": "CAPTURE123", "status": "REFUNDED"}
    ):
        services.process_paypal_event(event)
    order.refresh_from_db()
    assert order.status == "refunded" and order.phone.state == "retired"


def test_refund_uses_paypal_capture_and_confirmation(rental):
    order = reserve(rental)
    with patch.object(paypal, "get_order", return_value=remote_order(order)):
        services.complete_paypal_order(order.pk)
    services.request_refund(order.pk, rental[0], "No SMS received")
    with (
        patch.object(paypal, "refund", return_value={"status": "PENDING"}),
        pytest.raises(ValidationError),
    ):
        services.refund_order(order.pk, rental[0])
    with (
        patch.object(
            paypal,
            "refund",
            return_value={
                "status": "COMPLETED",
                "amount": {"currency_code": "USD", "value": "130.00"},
            },
        ),
        patch("virtual_numbers.services.stripe.Refund.create") as stripe_refund,
    ):
        services.refund_order(order.pk, rental[0])
    stripe_refund.assert_not_called()
    order.refresh_from_db()
    assert order.status == "refunded"


def test_paypal_transport_keeps_secrets_server_side_and_stable_request_id(settings):
    from unittest.mock import Mock

    settings.PAYPAL_MODE = "sandbox"
    settings.PAYPAL_CLIENT_ID = "merchant-client"
    settings.PAYPAL_CLIENT_SECRET = "private-secret"
    token = Mock()
    token.json.return_value = {"access_token": "server-only-token"}
    response = Mock(status_code=201, content=b"{}")
    response.json.return_value = {"id": "P123"}
    with (
        patch.object(paypal.requests, "post", return_value=token) as oauth,
        patch.object(paypal.requests, "request", return_value=response) as http,
    ):
        paypal.request(
            "POST",
            "/v2/checkout/orders",
            payload={"intent": "CAPTURE"},
            key="same-order",
        )
        paypal.request(
            "POST",
            "/v2/checkout/orders",
            payload={"intent": "CAPTURE"},
            key="same-order",
        )
    assert oauth.call_args.args[0] == "https://api-m.sandbox.paypal.com/v1/oauth2/token"
    assert oauth.call_args.kwargs["auth"] == ("merchant-client", "private-secret")
    assert (
        http.call_args_list[0].kwargs["headers"]["PayPal-Request-Id"]
        == http.call_args_list[1].kwargs["headers"]["PayPal-Request-Id"]
    )
    assert http.call_args.kwargs["allow_redirects"] is False


def test_webhook_verification_binds_configured_app(settings):
    settings.PAYPAL_WEBHOOK_ID = "configured-hook"
    headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api.paypal.com/cert",
        "PAYPAL-TRANSMISSION-ID": "transmission",
        "PAYPAL-TRANSMISSION-SIG": "signature",
        "PAYPAL-TRANSMISSION-TIME": "2026-09-22T12:00:00Z",
    }
    event = {"id": "WH1"}
    with patch.object(
        paypal, "request", return_value={"verification_status": "SUCCESS"}
    ) as verify:
        assert paypal.verify_webhook(event, headers)
    assert verify.call_args.kwargs["payload"]["webhook_id"] == "configured-hook"
    assert verify.call_args.kwargs["payload"]["webhook_event"] == event
    with patch.object(
        paypal, "request", return_value={"verification_status": "FAILURE"}
    ):
        assert not paypal.verify_webhook(event, headers)
