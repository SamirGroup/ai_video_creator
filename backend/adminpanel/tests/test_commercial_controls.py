from decimal import Decimal

import pytest
from accounts.tests.factories import UserFactory
from billing.models import Plan
from django.core.management import call_command
from providers.models import ApiCredentialConfig
from rest_framework.test import APIClient

from adminpanel.serializers import AdminPlanSerializer, AdminProviderSerializer

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "bad"])
def test_invalid_budget_rejected(amount):
    serializer = AdminPlanSerializer(
        Plan.objects.get(code="start"),
        data={"features": {"job_budget_usd": amount}},
        partial=True,
    )
    assert not serializer.is_valid()


def test_unknown_model_rejected():
    serializer = AdminPlanSerializer(
        Plan.objects.get(code="start"),
        data={"features": {"video_models": ["invented"]}},
        partial=True,
    )
    assert not serializer.is_valid()


def test_higgsfield_activation_requires_credentials(monkeypatch):
    call_command("seed_higgsfield")
    row = ApiCredentialConfig.objects.filter(provider="higgsfield").first()
    monkeypatch.delenv("HF_KEY", raising=False)
    s = AdminProviderSerializer(row, data={"is_active": True}, partial=True)
    assert not s.is_valid()


def test_superadmin_updates_plan_but_creator_cannot():
    plan = Plan.objects.get(code="start")
    c = APIClient()
    c.force_authenticate(UserFactory(is_superuser=True, is_totp_enabled=True))
    response = c.patch(
        f"/api/v1/admin/plans/{plan.pk}",
        {
            "videos_per_period": 12,
            "features": {**plan.features, "job_budget_usd": "2.50"},
        },
        format="json",
    )
    assert response.status_code == 200
    plan.refresh_from_db()
    assert plan.videos_per_period == 12 and Decimal(
        plan.features["job_budget_usd"]
    ) == Decimal("2.50")
    c.force_authenticate(UserFactory())
    assert (
        c.patch(
            f"/api/v1/admin/plans/{plan.pk}", {"price_amount": "1"}, format="json"
        ).status_code
        == 403
    )
