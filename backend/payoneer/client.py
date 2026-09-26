"""HTTP clients for Payoneer Checkout (accepting) and Mass Payouts (paying).

Checkout follows the Server Payment API (`LIST` sessions, hosted page):
https://developer.payoneer.com/checkout/yaml/checkout-server-payment-api.yaml
Mass Payouts follows API v4 (`/v4/programs/{program_id}/...`).

Provider responses can contain payer data, so errors never carry the body.
"""

from decimal import Decimal
from urllib.parse import quote

import requests
from django.core.cache import cache
from rest_framework.exceptions import APIException

CHECKOUT_HOSTS = {
    "sandbox": "https://api.sandbox.oscato.com/api",
    "live": "https://api.live.oscato.com/api",
}
PAYOUT_HOSTS = {
    "sandbox": "https://api.sandbox.payoneer.com",
    "live": "https://api.payoneer.com",
}
LOGIN_HOSTS = {
    "sandbox": "https://login.sandbox.payoneer.com",
    "live": "https://login.payoneer.com",
}
REDIRECT_HOSTS = (".oscato.com", ".payoneer.com")
TIMEOUT = (5, 25)
PAID_STATUSES = {"charged"}
# A CHARGE that has been paid out again has been refunded.
REFUNDED_STATUS = "paid_out"
NOTIFICATION_HEADER = "X-Creator-Notification-Token"


class PayoneerUnavailable(APIException):
    status_code = 503
    default_detail = "Payoneer is unavailable. Retry the same request later."
    default_code = "payoneer_unavailable"


class PayoneerRejected(APIException):
    status_code = 502
    default_detail = "Payoneer rejected the request."
    default_code = "payoneer_rejected"


def _send(method, url, **kwargs):
    try:
        response = requests.request(
            method, url, timeout=TIMEOUT, allow_redirects=False, **kwargs
        )
    except requests.RequestException:
        raise PayoneerUnavailable() from None
    if response.status_code in (401, 403):
        raise PayoneerRejected("Payoneer refused the credentials.")
    if response.status_code == 404:
        return None
    if response.status_code >= 500:
        raise PayoneerUnavailable()
    if response.status_code >= 400:
        raise PayoneerRejected(f"Payoneer rejected the request ({response.status_code}).")
    try:
        return response.json() if response.content else {}
    except ValueError:
        raise PayoneerUnavailable() from None


def _money(value):
    return float(Decimal(value).quantize(Decimal("0.01")))


# --- Checkout -----------------------------------------------------------------


def checkout_request(account, method, path, payload=None):
    if not account.checkout_ready:
        raise PayoneerUnavailable("This Payoneer account is not set up for checkout.")
    return _send(
        method,
        CHECKOUT_HOSTS[account.environment] + path,
        auth=(account.merchant_code, account.payment_token_enc),
        json=payload,
        headers={"Accept": "application/vnd.optile.payment.enterprise-v1-extensible+json"},
    )


def create_session(account, *, transaction_id, amount, currency, reference, product,
                   customer, callback, language="en_US"):
    """Open a hosted `LIST` session; returns (longId, redirect URL)."""
    result = checkout_request(
        account,
        "POST",
        "/lists",
        {
            "transactionId": transaction_id,
            "integration": "HOSTED",
            "operationType": "CHARGE",
            "division": account.division,
            "country": customer["country"],
            "customer": {
                "number": customer["number"],
                "email": customer["email"],
                "name": {
                    "firstName": customer["first_name"],
                    "lastName": customer["last_name"],
                },
                "addresses": {
                    "billing": {
                        "street": customer["street"],
                        "city": customer["city"],
                        "country": customer["country"],
                        "name": {
                            "firstName": customer["first_name"],
                            "lastName": customer["last_name"],
                        },
                    }
                },
            },
            "payment": {
                "amount": _money(amount),
                "currency": currency,
                "reference": reference[:40],
                "invoiceId": transaction_id,
            },
            "products": [
                {
                    "code": product["code"],
                    "name": product["name"][:100],
                    "amount": _money(amount),
                    "currency": currency,
                    "quantity": 1,
                    "type": "SERVICE",
                }
            ],
            "style": {"language": language, "hostedVersion": "v5"},
            "callback": {
                **callback,
                "notificationHeaders": [
                    {"name": NOTIFICATION_HEADER, "value": account.notification_token_enc}
                ],
            },
        },
    )
    long_id = (result or {}).get("identification", {}).get("longId", "")
    url = (result or {}).get("redirect", {}).get("url", "")
    if not long_id or not _trusted_redirect(url):
        raise PayoneerUnavailable("Payoneer did not return a payment page.")
    return long_id, url


def _trusted_redirect(url):
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.scheme == "https" and any(
        (parsed.hostname or "").endswith(host) for host in REDIRECT_HOSTS
    )


def get_session(account, long_id):
    return checkout_request(account, "GET", f"/lists/{quote(long_id, safe='')}")


def get_charge(account, long_id):
    return checkout_request(account, "GET", f"/charges/{quote(long_id, safe='')}")


def refund_charge(account, charge_id, *, transaction_id, amount, currency, reference):
    return checkout_request(
        account,
        "POST",
        f"/charges/{quote(charge_id, safe='')}/payout",
        {
            "transactionId": f"{transaction_id}-refund",
            "payment": {
                "amount": _money(amount),
                "currency": currency,
                "reference": reference[:40],
            },
        },
    )


def check_checkout(account):
    """A read-only call proving the merchant code and token are accepted."""
    checkout_request(account, "GET", "/meta/divisions")


# --- Mass Payouts ---------------------------------------------------------------


def _payout_token(account):
    key = f"payoneer-token:{account.pk}:{account.updated_at.timestamp()}"
    token = cache.get(key)
    if token:
        return token
    result = _send(
        "POST",
        LOGIN_HOSTS[account.environment] + "/api/v2/oauth2/token",
        auth=(account.client_id, account.client_secret_enc),
        data={"grant_type": "client_credentials", "scope": "read write"},
    )
    token = (result or {}).get("access_token")
    if not token:
        raise PayoneerRejected("Payoneer did not issue an access token.")
    cache.set(key, token, max(60, int((result or {}).get("expires_in", 3600)) - 120))
    return token


def payout_request(account, method, path, payload=None):
    if not account.payouts_ready:
        raise PayoneerUnavailable("This Payoneer account is not set up for payouts.")
    base = f"{PAYOUT_HOSTS[account.environment]}/v4/programs/{quote(account.program_id, safe='')}"
    return _send(
        method,
        base + path,
        headers={"Authorization": f"Bearer {_payout_token(account)}"},
        json=payload,
    )


def registration_link(account, payee_id, redirect_url, language="en"):
    result = payout_request(
        account,
        "POST",
        "/payees/registration-link",
        {"payee_id": payee_id, "redirect_url": redirect_url, "language_id": language},
    )
    link = (result or {}).get("result", result or {}).get("registration_link", "")
    if not _trusted_redirect(link):
        raise PayoneerUnavailable("Payoneer did not return a registration link.")
    return link


def payee_status(account, payee_id):
    result = payout_request(
        account, "GET", f"/payees/{quote(payee_id, safe='')}/status"
    )
    if result is None:
        return ""
    status = (result.get("result") or result).get("status") or {}
    return str(status.get("description") if isinstance(status, dict) else status)


def submit_payout(account, *, reference, payee_id, amount, currency, description):
    return payout_request(
        account,
        "POST",
        "/masspayouts",
        {
            "Payments": [
                {
                    "client_reference_id": reference,
                    "payee_id": payee_id,
                    "amount": _money(amount),
                    "currency": currency,
                    "description": description[:200],
                }
            ]
        },
    )


def payout_status(account, reference):
    result = payout_request(
        account, "GET", f"/payouts/{quote(reference, safe='')}/status"
    )
    return None if result is None else (result.get("result") or result)


def check_payouts(account):
    _payout_token(account)
