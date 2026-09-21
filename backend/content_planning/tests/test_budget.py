from decimal import Decimal
import pytest
from django.core.management import call_command
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from billing.models import Plan, AIWallet
from billing.tests.factories import SubscriptionFactory
from accounts.tests.factories import UserFactory
from providers.models import ApiCredentialConfig
from content_planning.budget import planning_budget, assert_plan_budget

pytestmark = pytest.mark.django_db


def test_catalog_seed_is_idempotent_and_never_activates():
    call_command("seed_higgsfield")
    row = ApiCredentialConfig.objects.get(
        provider="higgsfield", model_name="kling-video/v3.0/pro/text-to-video"
    )
    row.unit_cost_usd = Decimal("0.12")
    row.save()
    call_command("seed_higgsfield")
    row.refresh_from_db()
    assert row.unit_cost_usd == Decimal("0.12") and not row.is_active
    r = APIClient().get("/api/v1/video-models")
    assert r.status_code == 200
    item = next(x for x in r.data if x["model"] == row.model_name)
    assert item["credits_per_unit"] == 1200 and not item["available"]
    assert "secret_ref" not in item


def test_budget_uses_unreserved_balance_and_rejects_unconfigured_or_unentitled_model():
    call_command("seed_higgsfield")
    user = UserFactory()
    plan = Plan.objects.get(code="start")
    SubscriptionFactory(user=user, plan=plan)
    AIWallet.objects.create(user=user, balance_usd=14, reserved_usd=7)
    assert planning_budget(user)["max_count"] == 1
    with pytest.raises(ValidationError):
        assert_plan_budget(user, 1, "not-in-plan")
    with pytest.raises(ValidationError):
        assert_plan_budget(user, 1, "kling-video/v3.0/std/text-to-video")
    c = APIClient()
    c.force_authenticate(user)
    assert c.get("/api/v1/me/planning-budget").status_code == 200
