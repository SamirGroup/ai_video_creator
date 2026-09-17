import hashlib
import hmac
import json
from urllib.parse import urlencode
from unittest.mock import patch
import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from telegram_integration.models import TelegramConfig, TelegramIdentity
from telegram_integration.client import validate_init_data
from accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def cfg(settings):
    settings.TELEGRAM_BOT_TOKEN = "test-token"
    return TelegramConfig.objects.create(pk=1, enabled=True)


def signed(now=1000):
    data = {
        "auth_date": str(now),
        "user": json.dumps({"id": 123, "first_name": "Creator"}),
    }
    key = hmac.new(b"WebAppData", b"test-token", hashlib.sha256).digest()
    data["hash"] = hmac.new(
        key,
        "\n".join(f"{k}={v}" for k, v in sorted(data.items())).encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(data)


def test_telegram_signature_age_and_duplicate_fields(cfg):
    assert validate_init_data(signed(), now=1001)["id"] == 123
    for raw, now in [
        (signed() + "&auth_date=1000", 1001),
        (signed().replace("Creator", "Attacker"), 1001),
        (signed(), 1400),
        (signed(), 900),
    ]:
        with pytest.raises(ValidationError):
            validate_init_data(raw, now=now)


def test_webhook_requires_secret_even_with_valid_json(cfg, settings):
    settings.TELEGRAM_WEBHOOK_SECRET = "expected-secret"
    response = APIClient().post(
        "/api/v1/telegram/webhook", {"update_id": 1}, format="json"
    )
    assert response.status_code == 403


def test_creator_cannot_change_archive_config(cfg):
    client = APIClient()
    client.force_authenticate(UserFactory())
    assert (
        client.patch(
            "/api/v1/admin/telegram", {"enabled": False}, format="json"
        ).status_code
        == 403
    )


def test_cannot_link_another_creators_telegram(cfg):
    first = UserFactory()
    second = UserFactory()
    TelegramIdentity.objects.create(user=first, telegram_id=123)
    client = APIClient()
    client.force_authenticate(second)
    with patch(
        "telegram_integration.views.validate_init_data", return_value={"id": 123}
    ):
        assert (
            client.post(
                "/api/v1/telegram/link", {"init_data": "signed"}, format="json"
            ).status_code
            == 400
        )


def test_private_video_archive_round_trip_is_checksummed(cfg):
    from telegram_integration.archive import archive_video, restore
    from telegram_integration.models import TelegramArchive
    from core.storage import get_storage
    from video_pipeline.tests.factories import VideoJobFactory

    source = b"video-content-for-local-archive-test"
    digest = hashlib.sha256(source).hexdigest()
    job = VideoJobFactory(
        final_video_s3_key="roundtrip/video.mp4", moderation_approved_sha256=digest
    )
    get_storage().put_bytes(job.final_video_s3_key, source)
    saved = {}

    def api(method, payload, files=None):
        if files:
            field = next(iter(files))
            file_id = str(len(saved))
            saved[file_id] = files[field][1]
            assert (
                str(job.user_id) in payload["caption"]
                and str(job.pk) in payload["caption"]
            )
            return {field: {"file_id": file_id}, "message_id": len(saved)}
        return {"file_path": payload["file_id"]}

    class Download:
        def __init__(self, data):
            self.content = data

        def raise_for_status(self):
            pass

    with (
        patch("telegram_integration.archive.CHUNK_SIZE", 10),
        patch("telegram_integration.archive.call", side_effect=api),
    ):
        assert archive_video(str(job.pk))["status"] == "ready"
        assert len(TelegramArchive.objects.get(job=job).parts) == 4
        get_storage().delete(job.final_video_s3_key)
        with patch(
            "telegram_integration.archive.requests.get",
            side_effect=lambda url, **kw: Download(saved[url.rsplit("/", 1)[-1]]),
        ):
            restore(job)
    assert get_storage().get_bytes(job.final_video_s3_key) == source


def test_stars_precheckout_and_duplicate_payment(cfg, settings):
    from billing.models import Plan, AIWallet
    from telegram_integration.models import StarsOrder

    settings.TELEGRAM_WEBHOOK_SECRET = "expected-secret"
    user = UserFactory()
    order = StarsOrder.objects.create(
        user=user,
        plan=Plan.objects.get(code="start"),
        telegram_id=123,
        stars=2000,
        net_usd=20,
        tax_usd="2.40",
    )
    client = APIClient()
    headers = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "expected-secret"}
    pre = {
        "update_id": 90,
        "pre_checkout_query": {
            "id": "pre_1",
            "invoice_payload": str(order.pk),
            "from": {"id": 123},
            "currency": "XTR",
            "total_amount": 2000,
        },
    }
    with patch("telegram_integration.views.call") as api:
        assert (
            client.post(
                "/api/v1/telegram/webhook", pre, format="json", **headers
            ).status_code
            == 200
        )
        assert api.call_args.args[1]["ok"] == "true"
        pre["update_id"] = 91
        pre["pre_checkout_query"]["id"] = "pre_2"
        assert (
            client.post(
                "/api/v1/telegram/webhook", pre, format="json", **headers
            ).status_code
            == 200
        )
        assert api.call_args.args[1]["ok"] == "false"
    payment = {
        "update_id": 92,
        "message": {
            "from": {"id": 123},
            "successful_payment": {
                "invoice_payload": str(order.pk),
                "currency": "XTR",
                "total_amount": 2000,
                "telegram_payment_charge_id": "tg_charge",
            },
        },
    }
    assert (
        client.post(
            "/api/v1/telegram/webhook", payment, format="json", **headers
        ).status_code
        == 200
    )
    payment["update_id"] = 93
    assert (
        client.post(
            "/api/v1/telegram/webhook", payment, format="json", **headers
        ).status_code
        == 200
    )
    assert AIWallet.objects.get(user=user).balance_usd == 14
    assert user.subscription.plan.code == "start"


def test_superadmin_without_totp_must_complete_two_factor():
    from accounts.twofactor import requires_2fa_for_login

    user = UserFactory(is_superuser=True, is_totp_enabled=False)
    assert requires_2fa_for_login(user)
    client = APIClient()
    client.force_authenticate(user)
    assert client.get("/api/v1/admin/telegram").status_code == 403
