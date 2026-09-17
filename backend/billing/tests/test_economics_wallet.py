from decimal import Decimal
from unittest.mock import Mock, patch
import pytest
from billing.economics import quote
from billing.models import AIWallet, AIWalletEntry, Plan
from billing.tests.factories import SubscriptionFactory
from billing.wallet import (
    credit_payment,
    reserve_job,
    release_job,
    ensure_job_call_budget,
)
from providers.models import ApiUsageLog
from rest_framework.exceptions import PermissionDenied
from video_pipeline.tests.factories import VideoJobFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "code,net,tax,total,budget",
    [
        ("start", "20", "2.40", "22.40", "14.00"),
        ("pro", "50", "6.00", "56.00", "35.00"),
        ("pro_max", "100", "12.00", "112.00", "70.00"),
        ("ultra", "200", "24.00", "224.00", "140.00"),
    ],
)
def test_seeded_plan_economics(code, net, tax, total, budget):
    result = quote(Plan.objects.get(code=code))
    assert Decimal(result["net"]) == Decimal(net)
    assert (
        result["tax"] == tax
        and result["total"] == total
        and result["ai_budget_usd"] == budget
    )
    assert Decimal(result["platform_usd"]) + Decimal(budget) == Decimal(net)


def test_discount_reduces_ai_budget_and_tax():
    plan = Plan.objects.get(code="start")
    plan.discount_pct = Decimal("25")
    result = quote(plan)
    assert result["net"] == "15.00" and result["tax"] == "1.80"
    assert result["ai_budget_usd"] == "10.50"


def test_paid_credit_is_idempotent_and_usage_releases_reserved_money():
    job = VideoJobFactory()
    SubscriptionFactory(
        user=job.user, plan=Plan.objects.get(code="start"), status="active"
    )
    credit_payment(job.user, "invoice-test", Decimal("20"))
    credit_payment(job.user, "invoice-test", Decimal("20"))
    reserve_job(job)
    wallet = AIWallet.objects.get(user=job.user)
    assert wallet.balance_usd == 14 and wallet.reserved_usd == 7
    ApiUsageLog.objects.create(
        user=job.user,
        job=job,
        service="video_gen",
        provider="runway",
        operation="test",
        cost_usd=Decimal("0.60"),
    )
    wallet.refresh_from_db()
    assert wallet.balance_usd == Decimal("13.40") and wallet.reserved_usd == Decimal(
        "6.40"
    )
    release_job(job)
    release_job(job)
    wallet.refresh_from_db()
    assert wallet.reserved_usd == 0 and wallet.balance_usd == Decimal("13.40")
    assert AIWalletEntry.objects.filter(wallet=wallet).count() == 2


def test_unfunded_generation_fails_before_provider():
    job = VideoJobFactory()
    SubscriptionFactory(
        user=job.user, plan=Plan.objects.get(code="start"), status="active"
    )
    with pytest.raises(PermissionDenied):
        reserve_job(job)
    credit_payment(job.user, "invoice-cap", 20)
    reserve_job(job)
    with pytest.raises(PermissionDenied):
        ensure_job_call_budget(job, Decimal("8"))


def test_checkout_uses_edited_price_and_exclusive_tax():
    from billing.services import create_checkout_session

    job = VideoJobFactory()
    plan = Plan.objects.get(code="pro")
    plan.price_amount = Decimal("60")
    plan.discount_pct = Decimal("10")
    SubscriptionFactory(user=job.user, plan=plan, stripe_customer_id="cus_test")
    stripe = Mock()
    stripe.TaxRate.create.return_value.id = "txr_12"
    with patch("billing.services._stripe", return_value=stripe):
        create_checkout_session(
            user=job.user,
            plan=plan,
            success_url="https://example.test/success",
            cancel_url="https://example.test/cancel",
        )
    item = stripe.checkout.Session.create.call_args.kwargs["line_items"][0]
    assert item["price_data"]["unit_amount"] == 5400 and item["tax_rates"] == ["txr_12"]
    assert stripe.TaxRate.create.call_args.kwargs["inclusive"] is False


def test_partial_and_replayed_refunds_cannot_leave_free_credit():
    from billing.wallet import reverse_stripe_refund

    job = VideoJobFactory()
    credit_payment(job.user, "stripe:in_refund", 20)
    charge = {
        "id": "ch_refund",
        "invoice": "in_refund",
        "amount": 2240,
        "amount_refunded": 1120,
    }
    reverse_stripe_refund(charge)
    reverse_stripe_refund(charge)
    assert AIWallet.objects.get(user=job.user).balance_usd == 7
    charge["amount_refunded"] = 2240
    reverse_stripe_refund(charge)
    assert AIWallet.objects.get(user=job.user).balance_usd == 0


@pytest.mark.parametrize(
    "model,duration,price",
    [("gen4.5", 5, "0.12"), ("veo3.1_fast", 6, "0.10"), ("veo3.1", 6, "0.20")],
)
def test_catalog_models_use_documented_payloads(model, duration, price):
    from providers.models import ApiCredentialConfig
    from video_pipeline.services.video_gen_client import RunwayClient

    config = ApiCredentialConfig.objects.get(provider="runway", model_name=model)
    session = Mock()
    session.request.return_value.status_code = 200
    session.request.return_value.headers = {}
    session.request.return_value.json.return_value = {"id": "task"}
    result = RunwayClient(config, api_key="test-key", session=session).create_task(
        prompt="Original landscape", target_duration_sec=5
    )
    payload = session.request.call_args.kwargs["json"]
    assert payload["model"] == model and result.duration_sec == duration
    assert config.unit_cost_usd == Decimal(price)
    if model.startswith("veo"):
        assert payload["audio"] is False


def test_visual_request_is_not_charged_twice_on_download_retry():
    from providers.models import ApiCredentialConfig
    from providers.services import record_api_usage

    job = VideoJobFactory()
    SubscriptionFactory(
        user=job.user, plan=Plan.objects.get(code="start"), status="active"
    )
    credit_payment(job.user, "payment-visual", 20)
    reserve_job(job)
    config = ApiCredentialConfig.objects.get(provider="runway", model_name="gen4.5")
    kwargs = dict(
        config=config,
        operation="visual_generation",
        job=job,
        user=job.user,
        units=5,
        cost_usd=Decimal(".60"),
        request_id="runway-task-unique",
    )
    first = record_api_usage(**kwargs)
    second = record_api_usage(**kwargs)
    assert first.pk == second.pk
    assert AIWallet.objects.get(user=job.user).balance_usd == Decimal("13.40")


def test_paid_stage_excludes_a_second_worker():
    import psycopg
    from django.db import connection
    from providers.exceptions import ProviderRetryableError
    from video_pipeline.services.stage_lock import serialized_paid_stage

    job = VideoJobFactory()
    db = connection.settings_dict
    with psycopg.connect(
        dbname=db["NAME"],
        user=db["USER"],
        password=db["PASSWORD"],
        host=db["HOST"],
        port=db["PORT"],
    ) as other:
        key = job.pk.int % (2**63)
        other.execute("SELECT pg_advisory_lock(%s)", [key])
        called = []
        guarded = serialized_paid_stage(lambda value: called.append(value.pk))
        with pytest.raises(ProviderRetryableError):
            guarded(job)
        assert not called
        other.execute("SELECT pg_advisory_unlock(%s)", [key])
        guarded(job)
        assert called == [job.pk]
