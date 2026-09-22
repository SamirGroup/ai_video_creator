"""Payment-method readiness for dedicated number rentals; no secrets are returned."""

from django.conf import settings
from rest_framework.exceptions import APIException


class GatewayUnavailable(APIException):
    status_code = 503
    default_detail = "Payment provider is unavailable. Retry the same order later."
    default_code = "payment_provider_unavailable"


def stripe_key():
    return settings.VIRTUAL_NUMBERS_STRIPE_SECRET_KEY or settings.STRIPE_SECRET_KEY


def payment_methods():
    stripe_ready = bool(
        settings.NUMBER_PAYMENTS_STRIPE_ENABLED
        and stripe_key()
        and settings.VIRTUAL_NUMBERS_STRIPE_WEBHOOK_SECRET
    )
    paypal_ready = bool(
        settings.PAYPAL_ENABLED
        and settings.PAYPAL_MODE in ("sandbox", "live")
        and settings.PAYPAL_CLIENT_ID
        and settings.PAYPAL_CLIENT_SECRET
        and settings.PAYPAL_MERCHANT_ID
        and settings.PAYPAL_WEBHOOK_ID
    )
    return [
        {
            "code": "stripe",
            "label": "Visa / Mastercard · Stripe",
            "available": stripe_ready,
            "mode": "live" if stripe_key().startswith("sk_live_") else "test",
            "reason": "" if stripe_ready else "credentials_required",
        },
        {
            "code": "paypal",
            "label": "PayPal",
            "available": paypal_ready,
            "mode": settings.PAYPAL_MODE,
            "reason": "" if paypal_ready else "credentials_required",
        },
        {
            "code": "allpay",
            "label": "allpay.net · Gateway Plus",
            "available": False,
            "mode": "not_connected",
            "reason": "contract_and_api_spec_required",
        },
    ]


def require_gateway(code):
    method = next((m for m in payment_methods() if m["code"] == code), None)
    if not method or not method["available"]:
        raise GatewayUnavailable("This payment method has not been connected yet.")
