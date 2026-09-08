"""Checkout/portal session creation (FR-22) and the FR-70 revenue-share
service-fee invoice helper (Q1 service-fee model). All Stripe API calls are
mocked — no real network access (NFR-38).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.tests.factories import UserFactory
from billing import services
from billing.models import Subscription
from billing.tests.factories import PlanFactory, SubscriptionFactory
from contracts.models import Contract, ContractVersion
from revenue.models import InvoiceStatus, RevenueShareStatement, StatementStatus

pytestmark = pytest.mark.django_db


class TestCheckoutSession:
    def test_checkout_session_rejects_unknown_plan(self):
        user = UserFactory()
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(reverse("billing:checkout-session"), {"plan_code": "does-not-exist"}, format="json")

        assert response.status_code == 400

    def test_checkout_session_requires_a_configured_stripe_price(self):
        user = UserFactory()
        plan = PlanFactory(code="free_no_price", stripe_price_id="")
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(reverse("billing:checkout-session"), {"plan_code": plan.code}, format="json")

        assert response.status_code == 409

    def test_checkout_session_creates_stripe_session_and_returns_url(self):
        user = UserFactory()
        plan = PlanFactory(code="starter")
        client = APIClient()
        client.force_authenticate(user=user)

        fake_session = MagicMock(id="cs_test_1", url="https://checkout.stripe.com/cs_test_1")
        fake_customer = MagicMock(id="cus_test_1")

        with patch("billing.services.stripe.Customer.create", return_value=fake_customer), patch(
            "billing.services.stripe.checkout.Session.create", return_value=fake_session
        ) as mock_create:
            response = client.post(reverse("billing:checkout-session"), {"plan_code": plan.code}, format="json")

        assert response.status_code == 201
        assert response.data["checkout_url"] == fake_session.url
        mock_create.assert_called_once()
        subscription = Subscription.objects.get(user=user)
        assert subscription.stripe_customer_id == "cus_test_1"

    def test_checkout_session_requires_authentication(self):
        response = APIClient().post(reverse("billing:checkout-session"), {"plan_code": "starter"}, format="json")
        assert response.status_code == 401


class TestPortalSession:
    def test_portal_session_requires_existing_stripe_customer(self):
        user = UserFactory()
        SubscriptionFactory(user=user, stripe_customer_id="")
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(reverse("billing:portal-session"), {}, format="json")

        assert response.status_code == 409

    def test_portal_session_returns_url(self):
        user = UserFactory()
        SubscriptionFactory(user=user, stripe_customer_id="cus_existing")
        client = APIClient()
        client.force_authenticate(user=user)

        fake_session = MagicMock(url="https://billing.stripe.com/session/abc")
        with patch("billing.services.stripe.billing_portal.Session.create", return_value=fake_session):
            response = client.post(reverse("billing:portal-session"), {}, format="json")

        assert response.status_code == 200
        assert response.data["portal_url"] == fake_session.url


def _make_statement(user, amount: Decimal) -> RevenueShareStatement:
    version = ContractVersion.objects.create(
        version="v1-test",
        title="Creator Agreement",
        body_markdown="Terms...",
        effective_from="2026-01-01T00:00:00Z",
        is_active=True,
    )
    contract = Contract.objects.create(
        user=user,
        contract_version=version,
        ip_address="127.0.0.1",
        body_sha256=version.body_sha256,
        consent_revenue_share=True,
        consent_publish_to_channel=True,
        consent_data_processing=True,
    )
    return RevenueShareStatement.objects.create(
        user=user,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        gross_revenue=Decimal("100.00"),
        platform_share_amount=amount,
        creator_share_amount=Decimal("100.00") - amount,
        contract=contract,
        status=StatementStatus.FINALIZED,
    )


class TestRevenueShareInvoice:
    """FR-70/FR-70a/FR-70b: `create_revenue_share_invoice` — not yet wired to
    the (not-yet-built) revenue period-close job, but independently correct
    and testable.
    """

    def test_raises_without_a_stripe_customer(self):
        user = UserFactory()
        statement = _make_statement(user, Decimal("50.00"))

        with pytest.raises(services.RevenueShareInvoiceError):
            services.create_revenue_share_invoice(user, statement)

    def test_raises_without_saved_payment_method(self):
        user = UserFactory()
        SubscriptionFactory(user=user, stripe_customer_id="cus_1", default_payment_method_id="")
        statement = _make_statement(user, Decimal("50.00"))

        with pytest.raises(services.RevenueShareInvoiceError):
            services.create_revenue_share_invoice(user, statement)

    def test_raises_below_the_a10_minimum_threshold(self):
        user = UserFactory()
        SubscriptionFactory(user=user, stripe_customer_id="cus_1", default_payment_method_id="pm_1")
        statement = _make_statement(user, Decimal("5.00"))

        with pytest.raises(services.RevenueShareInvoiceError):
            services.create_revenue_share_invoice(user, statement)

    def test_creates_stripe_invoice_charges_it_and_writes_local_records(self):
        user = UserFactory()
        SubscriptionFactory(user=user, stripe_customer_id="cus_1", default_payment_method_id="pm_1")
        statement = _make_statement(user, Decimal("50.00"))

        fake_invoice = MagicMock(id="in_test_1", status="paid")
        fake_invoice.finalize_invoice.return_value = fake_invoice
        fake_invoice.pay.return_value = fake_invoice

        with patch("billing.services.stripe.InvoiceItem.create") as mock_item, patch(
            "billing.services.stripe.Invoice.create", return_value=fake_invoice
        ):
            invoice = services.create_revenue_share_invoice(user, statement)

        mock_item.assert_called_once()
        fake_invoice.finalize_invoice.assert_called_once()
        fake_invoice.pay.assert_called_once()
        assert invoice.status == InvoiceStatus.PAID
        assert invoice.amount == Decimal("50.00")
        assert invoice.stripe_invoice_id == "in_test_1"

        from revenue.models import LedgerEntry

        assert LedgerEntry.objects.filter(ref_id=invoice.id).exists()
