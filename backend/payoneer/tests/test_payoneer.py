from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from accounts.tests.factories import UserFactory
from payoneer import client
from payoneer.models import PayoneerAccount, PayoneerPayee, PayoneerPayout

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin(settings):
    settings.STAFF_2FA_REQUIRED = False
    api = APIClient()
    api.force_authenticate(UserFactory(is_superuser=True))
    return api


def create_account(admin, **extra):
    response = admin.post(
        "/api/v1/admin/payoneer/accounts",
        {
            "label": "Main",
            "environment": "sandbox",
            "checkout_enabled": True,
            "merchant_code": "M1",
            "division": "main",
            "payment_token": "secret-token",
            "payouts_enabled": True,
            "program_id": "100",
            "client_id": "cid",
            "client_secret": "csecret",
            **extra,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def test_admin_only(settings):
    settings.STAFF_2FA_REQUIRED = False
    api = APIClient()
    api.force_authenticate(UserFactory())
    assert api.get("/api/v1/admin/payoneer/accounts").status_code == 403


def test_secrets_are_write_only_and_kept_on_blank_update(admin):
    data = create_account(admin)
    assert "payment_token" not in data and data["payment_token_set"] is True
    assert data["checkout_ready"] and data["payouts_ready"]
    assert data["notification_url"].endswith(f"/webhooks/payoneer/{data['id']}/checkout")
    admin.patch(
        f"/api/v1/admin/payoneer/accounts/{data['id']}",
        {"payment_token": "", "label": "Renamed"},
        format="json",
    )
    account = PayoneerAccount.objects.get()
    assert account.payment_token_enc == "secret-token" and account.label == "Renamed"


def test_several_accounts_but_one_default_each(admin):
    first = create_account(admin, is_default_checkout=True)
    second = create_account(admin, label="Second", is_default_checkout=True)
    assert PayoneerAccount.objects.filter(is_default_checkout=True).get().pk.hex == second["id"].replace("-", "")
    assert PayoneerAccount.objects.count() == 2
    response = admin.patch(
        f"/api/v1/admin/payoneer/accounts/{first['id']}",
        {"is_default_payouts": True, "payouts_enabled": False},
        format="json",
    )
    assert response.status_code == 400


def test_payee_invite_and_payout_lifecycle(admin):
    account = create_account(admin)
    payee = admin.post(
        "/api/v1/admin/payoneer/payees",
        {"account": account["id"], "display_name": "Designer", "email": "d@example.com"},
        format="json",
    ).data
    assert payee["payee_id"].startswith("cai") and payee["status"] == "invited"
    link = "https://payouts.sandbox.payoneer.com/partners/lp.aspx?token=abc"
    with patch.object(client, "registration_link", return_value=link):
        assert admin.post(f"/api/v1/admin/payoneer/payees/{payee['id']}/invite").data == {
            "registration_link": link
        }
    new = {"payee": payee["id"], "amount": "250.00", "description": "Landing design"}
    assert admin.post("/api/v1/admin/payoneer/payouts", new, format="json").status_code == 400
    with patch.object(client, "payee_status", return_value="Active"):
        admin.post(f"/api/v1/admin/payoneer/payees/{payee['id']}/refresh")
    with patch.object(client, "submit_payout", side_effect=client.PayoneerUnavailable()):
        assert admin.post("/api/v1/admin/payoneer/payouts", new, format="json").status_code == 503
    payout = PayoneerPayout.objects.get()
    assert payout.status == "submitting"
    with patch.object(client, "submit_payout", return_value={"result": "ok"}) as submit:
        data = admin.post(f"/api/v1/admin/payoneer/payouts/{payout.pk}/submit").data
    assert data["status"] == "pending"
    assert submit.call_args.kwargs["reference"] == payout.client_reference_id
    with patch.object(client, "payout_status", return_value={"status": "Transferred", "payout_id": "P9"}):
        data = admin.post(f"/api/v1/admin/payoneer/payouts/{payout.pk}/refresh").data
    assert data["status"] == "transferred" and data["payout_id"] == "P9"


def test_payout_limit(admin, settings):
    settings.PAYONEER_PAYOUT_MAX_USD = "100"
    account = create_account(admin)
    payee = PayoneerPayee.objects.create(
        account_id=account["id"], display_name="X", payee_id="cai1", status="active"
    )
    response = admin.post(
        "/api/v1/admin/payoneer/payouts",
        {"payee": str(payee.pk), "amount": "101.00", "description": "Too much"},
        format="json",
    )
    assert response.status_code == 400 and not PayoneerPayout.objects.exists()


def test_create_session_builds_hosted_list_and_rejects_foreign_redirects(admin):
    create_account(admin)
    account = PayoneerAccount.objects.get()
    kwargs = dict(
        transaction_id="WS-2026-00001", amount="800.00", currency="USD", reference="Website",
        product={"code": "starter", "name": "Start"},
        customer={"number": "u1", "email": "a@b.c", "first_name": "A", "last_name": "B",
                  "street": "S", "city": "C", "country": "UZ"},
        callback={"returnUrl": "https://x/return", "cancelUrl": "https://x/cancel",
                  "notificationUrl": "https://x/n"},
    )
    good = {"identification": {"longId": "L1"}, "redirect": {"url": "https://pages.sandbox.oscato.com/p/L1"}}
    with patch.object(client, "_send", return_value=good) as send:
        assert client.create_session(account, **kwargs) == ("L1", good["redirect"]["url"])
    body = send.call_args.kwargs["json"]
    assert body["integration"] == "HOSTED" and body["payment"]["amount"] == 800.0
    assert body["callback"]["notificationHeaders"][0]["value"] == account.notification_token_enc
    assert send.call_args.kwargs["auth"] == ("M1", "secret-token")
    bad = {"identification": {"longId": "L1"}, "redirect": {"url": "https://evil.example/p"}}
    with patch.object(client, "_send", return_value=bad), pytest.raises(client.PayoneerUnavailable):
        client.create_session(account, **kwargs)
