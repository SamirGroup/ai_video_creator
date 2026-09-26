import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from accounts.tests.factories import UserFactory
from payoneer import client as payoneer
from payoneer.models import PayoneerAccount
from web_services.contract import amount_words, checksum, delivery
from web_services.models import ExecutorProfile, ServiceOrder, ServicePackage

pytestmark = pytest.mark.django_db

REDIRECT = "https://pages.sandbox.oscato.com/pay/LIST123"

RESIDENT = {
    "full_name": "Aliyev Vali G‘ani o‘g‘li",
    "date_of_birth": "1990-05-01",
    "passport_number": "AA1234567",
    "passport_issued_by": "Toshkent sh. IIB",
    "passport_issued_at": "2018-02-03",
    "pinfl": "12345678901234",
    "address": "Amir Temur ko‘chasi 1",
    "city": "Toshkent",
    "phone": "+998 90 123-45-67",
    "email": "vali@example.com",
}
FOREIGN = {
    **{k: v for k, v in RESIDENT.items() if k != "pinfl"},
    "full_name": "John Smith",
    "passport_number": "X1234567",
    "passport_issued_by": "HM Passport Office",
    "citizenship": "United Kingdom",
    "citizenship_code": "GB",
    "country": "United Kingdom",
    "country_code": "GB",
}
PROJECT = {"name": "Oshxona sayti", "description": "Restoran uchun menyu va bron qilish sahifasi."}


@pytest.fixture
def shop(settings):
    settings.STAFF_2FA_REQUIRED = False
    executor = ExecutorProfile.load()
    for field, value in {
        "legal_name": "«Creator AI» MChJ",
        "director_name": "Abdulxamidov S.A.",
        "address": "Toshkent sh., Chilonzor 1",
        "tin": "123456789",
        "phone": "+998901234567",
        "email": "info@example.com",
        "sales_enabled": True,
    }.items():
        setattr(executor, field, value)
    executor.save()
    account = PayoneerAccount.objects.create(
        label="Sandbox",
        checkout_enabled=True,
        is_default_checkout=True,
        merchant_code="MERCHANT",
        payment_token_enc="token",
        division="main",
    )
    user = UserFactory()
    api = APIClient()
    api.force_authenticate(user)
    return api, user, account


def preview(api, customer=RESIDENT, kind="resident", package="business"):
    response = api.post(
        "/api/v1/web-services/contract-preview",
        {"package": package, "contract_type": kind, "customer": customer, "project": PROJECT},
        format="json",
    )
    assert response.status_code == 200, response.data
    return response.data


def place(api, customer=RESIDENT, kind="resident", package="business", **extra):
    draft = preview(api, customer, kind, package)
    with patch.object(payoneer, "create_session", return_value=("LIST123", REDIRECT)) as create:
        response = api.post(
            "/api/v1/web-services/orders",
            {
                "package": package,
                "contract_type": kind,
                "customer": customer,
                "project": PROJECT,
                "request_key": str(uuid.uuid4()),
                "quoted_total": draft["document"]["price"],
                "preview_checksum": draft["checksum"],
                "accept_terms": True,
                **extra,
            },
            format="json",
        )
    return response, create


def charge(order, amount="1600.00", status="charged", reference=None):
    return {
        "status": {"code": status, "reason": status},
        "identification": {"longId": "CHARGE1", "transactionId": reference or order.number},
        "payment": {"amount": float(amount), "currency": "USD"},
    }


def test_public_catalog_lists_the_four_packages():
    data = APIClient().get("/api/v1/public/web-services").data
    assert [p["price_usd"] for p in data["packages"]] == ["800.00", "1600.00", "3200.00", "6400.00"]
    assert data["sales_ready"] is False and data["reason"] == "sales_paused"


def test_resident_contract_carries_package_terms_and_price(shop):
    document = preview(shop[0])["document"]
    assert document["language"] == "uz"
    text = str(document["sections"])
    assert "1600.00 AQSh dollari (bir ming olti yuz AQSh dollari 00 sent)" in text
    assert "bajarish muddati — 1 kun;" in text and "Korporativ sayt" in text
    assert "sun’iy intellekt texnologiyalaridan foydalangan holda" in text
    assert ["JShShIR", "12345678901234"] in document["customer_rows"]


def test_foreign_contract_is_english_and_rejects_uzbek_citizens(shop):
    document = preview(shop[0], FOREIGN, "non_resident", "enterprise")["document"]
    assert document["language"] == "en"
    assert "USD 6400.00 (six thousand four hundred US dollars 00 cents)" in str(document["sections"])
    assert "as per the specification" in str(document["sections"])
    response = shop[0].post(
        "/api/v1/web-services/contract-preview",
        {"package": "pro", "contract_type": "non_resident",
         "customer": {**FOREIGN, "citizenship_code": "UZ"}, "project": PROJECT},
        format="json",
    )
    assert response.status_code == 400


def test_resident_requires_pinfl(shop):
    response = shop[0].post(
        "/api/v1/web-services/contract-preview",
        {"package": "starter", "contract_type": "resident",
         "customer": {**RESIDENT, "pinfl": ""}, "project": PROJECT},
        format="json",
    )
    assert response.status_code == 400 and "pinfl" in str(response.data)


def test_order_freezes_contract_and_opens_payoneer(shop):
    api, user, account = shop
    response, create = place(api)
    assert response.status_code == 201, response.data
    order = ServiceOrder.objects.get()
    assert order.number.startswith("WS-") and order.number.endswith("-00001")
    assert response.data["checkout_url"] == REDIRECT
    kwargs = create.call_args.kwargs
    assert kwargs["amount"] == Decimal("1600.00") and kwargs["transaction_id"] == order.number
    assert kwargs["customer"]["country"] == "UZ"
    assert order.contract["number"] == order.number
    assert checksum(order.contract) == order.contract_sha256
    detail = api.get(f"/api/v1/web-services/orders/{order.pk}").data
    assert detail["contract"]["acceptance"]["checksum"] == order.contract_sha256


def test_changed_terms_require_a_fresh_review(shop):
    api = shop[0]
    draft = preview(api)
    ServicePackage.objects.filter(code="business").update(delivery_hours=30)
    response = api.post(
        "/api/v1/web-services/orders",
        {"package": "business", "contract_type": "resident", "customer": RESIDENT,
         "project": PROJECT, "request_key": str(uuid.uuid4()), "quoted_total": "1600.00",
         "preview_checksum": draft["checksum"], "accept_terms": True},
        format="json",
    )
    assert response.status_code == 400 and not ServiceOrder.objects.exists()


def test_terms_must_be_accepted(shop):
    response, _ = place(shop[0], accept_terms=False)
    assert response.status_code == 400


def test_notification_marks_paid_only_after_payoneer_confirms(shop):
    api, user, account = shop
    place(api)
    order = ServiceOrder.objects.get()
    url = f"/api/v1/webhooks/payoneer/{account.pk}/checkout"
    params = {"transactionId": order.number, "longId": "CHARGE1", "entity": "payment"}
    assert APIClient().post(url, params).status_code == 403
    assert (
        APIClient().post(url, params, HTTP_X_CREATOR_NOTIFICATION_TOKEN="wrong").status_code == 403
    )
    headers = {"HTTP_X_CREATOR_NOTIFICATION_TOKEN": account.notification_token_enc}
    with patch.object(payoneer, "get_charge", return_value=charge(order, "1.00")):
        assert APIClient().post(url, params, **headers).status_code == 503
    order.refresh_from_db()
    assert order.status == "pending_payment"
    with patch.object(payoneer, "get_charge", return_value=charge(order)):
        assert APIClient().post(url, params, **headers).status_code == 200
    order.refresh_from_db()
    assert order.status == "paid" and order.charge_id == "CHARGE1"


def test_browser_return_confirms_through_the_session(shop):
    api = shop[0]
    place(api)
    order = ServiceOrder.objects.get()
    with patch.object(payoneer, "get_session", return_value=charge(order, status="listed")):
        assert api.post(f"/api/v1/web-services/orders/{order.pk}/confirm").data["status"] == "pending_payment"
    with patch.object(payoneer, "get_session", return_value=charge(order)):
        assert api.post(f"/api/v1/web-services/orders/{order.pk}/confirm").data["status"] == "paid"


def test_admin_refund_and_status_flow(shop):
    api, user, account = shop
    place(api)
    order = ServiceOrder.objects.get()
    admin = APIClient()
    admin.force_authenticate(UserFactory(is_superuser=True))
    with patch.object(payoneer, "get_charge", return_value=charge(order)):
        from web_services.services import confirm_payment

        confirm_payment(order.pk, charge_id="CHARGE1")
    base = f"/api/v1/admin/web-services/orders/{order.pk}"
    assert api.get(base).status_code == 403
    assert admin.patch(base, {"status": "delivered"}, format="json").status_code == 400
    assert admin.patch(base, {"status": "in_progress"}, format="json").data["status"] == "in_progress"
    assert admin.get(base).data["contract"]["number"] == order.number
    refund = {"status": {"code": "paid_out"}}
    with patch.object(payoneer, "refund_charge", return_value=refund) as call:
        assert admin.post(f"{base}/refund").data["status"] == "refunded"
    assert call.call_args.kwargs["amount"] == Decimal("1600.00")


def test_sales_stay_closed_without_requisites_or_account(shop):
    api, user, account = shop
    account.is_default_checkout = False
    account.save()
    response, create = place(api)
    assert response.status_code == 400 and not create.called


def test_amount_words():
    assert amount_words("800", "uz") == "sakkiz yuz AQSh dollari 00 sent"
    assert amount_words("3200.50", "en") == "three thousand two hundred US dollars 50 cents"
    assert amount_words("1999999", "en").startswith("one million nine hundred ninety-nine thousand")


def test_delivery_wording_and_seeded_hours():
    hours = {p.code: (p.delivery_hours_min, p.delivery_hours) for p in ServicePackage.objects.all()}
    assert hours == {"starter": (1, 2), "business": (None, 24), "pro": (None, 48), "enterprise": (None, 72)}
    assert delivery({"delivery_hours_min": 1, "delivery_hours": 2}, "uz") == "1–2 soat"
    assert delivery({"delivery_hours_min": 1, "delivery_hours": 2}, "en") == "1–2 hours"
    assert delivery({"delivery_hours_min": None, "delivery_hours": 24}, "en") == "1 day"
    assert delivery({"delivery_hours_min": None, "delivery_hours": 72}, "uz") == "3 kun"
    assert delivery({"delivery_hours_min": None, "delivery_hours": 36}, "en") == "36 hours"
