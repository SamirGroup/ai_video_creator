"""PayPal Orders v2: hosted approval, server capture, verified webhooks, refunds."""

import uuid
from urllib.parse import quote, urlparse

import requests
from django.conf import settings

from virtual_numbers.gateways import GatewayUnavailable


def request(method, path, *, payload=None, key=None):
    if (
        settings.PAYPAL_MODE not in ("sandbox", "live")
        or not settings.PAYPAL_CLIENT_ID
        or not settings.PAYPAL_CLIENT_SECRET
    ):
        raise GatewayUnavailable("PayPal credentials are not configured.")
    base = (
        "https://api-m.paypal.com"
        if settings.PAYPAL_MODE == "live"
        else "https://api-m.sandbox.paypal.com"
    )
    try:
        token_response = requests.post(
            base + "/v1/oauth2/token",
            auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            timeout=(5, 20),
            allow_redirects=False,
        )
        token_response.raise_for_status()
        token = token_response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if key:
            headers["PayPal-Request-Id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, key))
        response = requests.request(
            method,
            base + path,
            headers=headers,
            json=payload,
            timeout=(5, 20),
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code not in (200, 201, 202, 204):
            raise GatewayUnavailable()
        return response.json() if response.content else {}
    except (requests.RequestException, KeyError, ValueError):
        # Provider responses can contain payer information; do not log or expose them.
        raise GatewayUnavailable() from None


def create_checkout(order):
    breakdown = order.price_breakdown
    amount = {"currency_code": "USD", "value": str(order.price_usd)}
    if breakdown:
        amount["breakdown"] = {
            "item_total": {"currency_code": "USD", "value": breakdown["subtotal"]},
            "tax_total": {"currency_code": "USD", "value": breakdown["tax"]},
        }
    unit = {
        "reference_id": str(order.pk),
        "custom_id": str(order.pk),
        "invoice_id": f"number-{order.pk}",
        "payee": {"merchant_id": settings.PAYPAL_MERCHANT_ID},
        "description": f"{order.offer_name} ({order.rental_days} days)"[:127],
        "amount": amount,
    }
    result = request(
        "POST",
        "/v2/checkout/orders",
        key=f"number-create:{order.pk}",
        payload={
            "intent": "CAPTURE",
            "purchase_units": [unit],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "shipping_preference": "NO_SHIPPING",
                        "user_action": "PAY_NOW",
                        "return_url": f"{settings.FRONTEND_BASE_URL}/virtual-numbers?paypal_order={order.pk}",
                        "cancel_url": f"{settings.FRONTEND_BASE_URL}/virtual-numbers?payment=canceled",
                    }
                }
            },
        },
    )
    url = next(
        (
            link["href"]
            for link in result.get("links", [])
            if link.get("rel") in ("payer-action", "approve")
        ),
        "",
    )
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname
        not in (
            "www.paypal.com",
            "www.sandbox.paypal.com",
            "paypal.com",
            "sandbox.paypal.com",
        )
        or not result.get("id")
    ):
        raise GatewayUnavailable("PayPal did not return a valid approval URL.")
    return result["id"], url


def get_order(checkout_id):
    return request("GET", f"/v2/checkout/orders/{quote(checkout_id, safe='')}")


def capture(order):
    return request(
        "POST",
        f"/v2/checkout/orders/{quote(order.checkout_id, safe='')}/capture",
        payload={},
        key=f"number-capture:{order.pk}",
    )


def get_capture(capture_id):
    return request("GET", f"/v2/payments/captures/{quote(capture_id, safe='')}")


def refund(order):
    return request(
        "POST",
        f"/v2/payments/captures/{quote(order.payment_intent, safe='')}/refund",
        key=f"number-refund:{order.pk}",
        payload={"amount": {"value": str(order.price_usd), "currency_code": "USD"}},
    )


def verify_webhook(event, headers):
    required = {
        "auth_algo": "PAYPAL-AUTH-ALGO",
        "cert_url": "PAYPAL-CERT-URL",
        "transmission_id": "PAYPAL-TRANSMISSION-ID",
        "transmission_sig": "PAYPAL-TRANSMISSION-SIG",
        "transmission_time": "PAYPAL-TRANSMISSION-TIME",
    }
    if not settings.PAYPAL_WEBHOOK_ID or any(
        not headers.get(name) for name in required.values()
    ):
        return False
    payload = {key: headers[name] for key, name in required.items()}
    payload.update({"webhook_id": settings.PAYPAL_WEBHOOK_ID, "webhook_event": event})
    return (
        request(
            "POST", "/v1/notifications/verify-webhook-signature", payload=payload
        ).get("verification_status")
        == "SUCCESS"
    )
