from datetime import date
from django.utils import timezone
from decimal import Decimal
import pytest
from rest_framework.test import APIClient
from accounts.tests.factories import UserFactory
from revenue.models import RevenueRecord, Invoice
from video_pipeline.tests.factories import VideoJobFactory

pytestmark = pytest.mark.django_db


def test_summary_deduplicates_providers_and_does_not_confirm_on_account_connection():
    job = VideoJobFactory()
    for source, amount in [("youtube_analytics", "10"), ("adsense", "12")]:
        RevenueRecord.objects.create(
            user=job.user,
            channel=job.channel,
            job=job,
            youtube_video_id="video-test",
            date=date.today(),
            source=source,
            estimated_revenue=Decimal(amount),
            is_final=False,
            synced_at=timezone.now(),
        )
    client = APIClient()
    client.force_authenticate(job.user)
    response = client.get("/api/v1/revenue/summary")
    assert response.status_code == 200
    assert Decimal(response.data["platform_generated"]["estimated_revenue"]) == Decimal(
        "12"
    )
    assert response.data["is_estimated"] is True
    daily = client.get("/api/v1/revenue/daily")
    assert Decimal(daily.data["days"][0]["estimated_revenue"]) == Decimal("12")


def test_invalid_dates_are_validation_errors():
    client = APIClient()
    client.force_authenticate(UserFactory())
    for params in [{"from": "bad"}, {"from": "2026-02-01", "to": "2026-01-01"}]:
        assert client.get("/api/v1/revenue/summary", params).status_code == 400


def test_invoice_endpoint_is_live_and_owner_scoped():
    user = UserFactory()
    stranger = UserFactory()
    invoice = Invoice.objects.create(
        user=user, kind="revenue_share", amount=10, status="open", due_at=timezone.now()
    )
    client = APIClient()
    client.force_authenticate(stranger)
    assert client.get("/api/v1/invoices").data == []
    assert client.get(f"/api/v1/invoices/{invoice.pk}/pdf").status_code == 404
    client.force_authenticate(user)
    assert client.get("/api/v1/invoices").data[0]["id"] == invoice.pk
    assert client.get(f"/api/v1/invoices/{invoice.pk}/pdf").content.startswith(b"%PDF")
