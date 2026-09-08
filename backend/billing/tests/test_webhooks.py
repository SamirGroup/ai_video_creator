"""Stripe webhook tests (FR-25, FR-26, NFR-5, AC-8).

Signature verification exercises the *real* `stripe.Webhook.construct_event`
(a manually HMAC-signed payload, using Stripe's own signing scheme) rather
than mocking it away — this genuinely proves "invalid signature -> 400,
state unchanged" (AC-8), not just that our code trusts whatever it's told.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.tests.factories import UserFactory
from billing.models import SubscriptionStatus, WebhookEvent
from billing.tests.factories import PlanFactory, SubscriptionFactory

pytestmark = pytest.mark.django_db

WEBHOOK_SECRET = "whsec_test_secret"


@pytest.fixture(autouse=True)
def _stripe_webhook_secret(settings):
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET


def _sign(payload: bytes, secret: str, timestamp: int) -> str:
    signed_payload = f"{timestamp}.".encode() + payload
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def _post_event(client, event: dict, *, secret: str = WEBHOOK_SECRET, bad_signature: bool = False):
    payload = json.dumps(event).encode()
    timestamp = int(time.time())
    sig_header = _sign(payload, "wrong-secret" if bad_signature else secret, timestamp)
    return client.generic(
        "POST",
        reverse("billing:stripe-webhook"),
        data=payload,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=sig_header,
    )


def _event(event_id: str, event_type: str, obj: dict) -> dict:
    return {"id": event_id, "object": "event", "type": event_type, "data": {"object": obj}}


class TestSignatureVerification:
    def test_invalid_signature_is_rejected_with_400_and_nothing_is_recorded(self):
        client = APIClient()
        event = _event("evt_bad_sig", "invoice.paid", {"id": "in_1", "customer": "cus_1"})

        response = _post_event(client, event, bad_signature=True)

        assert response.status_code == 400
        assert not WebhookEvent.objects.exists()

    def test_missing_signature_header_is_rejected_with_400(self):
        client = APIClient()
        payload = json.dumps(_event("evt_no_sig", "invoice.paid", {})).encode()

        response = client.generic(
            "POST", reverse("billing:stripe-webhook"), data=payload, content_type="application/json"
        )

        assert response.status_code == 400
        assert not WebhookEvent.objects.exists()

    def test_tampered_payload_after_signing_is_rejected(self):
        client = APIClient()
        payload = json.dumps(_event("evt_tampered", "invoice.paid", {"id": "in_1"})).encode()
        sig_header = _sign(payload, WEBHOOK_SECRET, int(time.time()))
        tampered_payload = payload.replace(b"in_1", b"in_2_evil")

        response = client.generic(
            "POST",
            reverse("billing:stripe-webhook"),
            data=tampered_payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=sig_header,
        )

        assert response.status_code == 400
        assert not WebhookEvent.objects.exists()


class TestIdempotency:
    def test_duplicate_event_id_is_recorded_and_applied_only_once(self):
        from revenue.models import LedgerEntry

        client = APIClient()
        user = UserFactory(email="dedupe@example.com")
        subscription = SubscriptionFactory(user=user, stripe_customer_id="cus_dedupe")
        event = _event(
            "evt_dup_1",
            "invoice.paid",
            {"id": "in_dup", "customer": "cus_dedupe", "amount_paid": 5000, "currency": "usd"},
        )

        first = _post_event(client, event)
        second = _post_event(client, event)

        assert first.status_code == 200
        assert second.status_code == 200
        assert WebhookEvent.objects.filter(event_id="evt_dup_1").count() == 1
        assert LedgerEntry.objects.filter(ref_id=subscription.id).count() == 1


class TestEventHandling:
    def test_checkout_session_completed_activates_subscription(self):
        client = APIClient()
        user = UserFactory(email="checkout@example.com")
        plan = PlanFactory(code="professional")
        subscription = SubscriptionFactory(user=user, status=SubscriptionStatus.TRIALING)
        event = _event(
            "evt_checkout_1",
            "checkout.session.completed",
            {
                "id": "cs_1",
                "customer": "cus_new",
                "subscription": "sub_new",
                "client_reference_id": str(user.id),
                "metadata": {"user_id": str(user.id), "plan_code": plan.code},
            },
        )

        response = _post_event(client, event)

        assert response.status_code == 200
        subscription.refresh_from_db()
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.stripe_customer_id == "cus_new"
        assert subscription.stripe_subscription_id == "sub_new"
        assert subscription.plan_id == plan.id

    def test_invoice_payment_failed_moves_active_subscription_to_past_due_with_grace_period(self):
        client = APIClient()
        user = UserFactory(email="pastdue@example.com")
        subscription = SubscriptionFactory(user=user, status=SubscriptionStatus.ACTIVE, stripe_customer_id="cus_pd")
        event = _event("evt_failed_1", "invoice.payment_failed", {"id": "in_failed", "customer": "cus_pd"})

        response = _post_event(client, event)

        assert response.status_code == 200
        subscription.refresh_from_db()
        assert subscription.status == SubscriptionStatus.PAST_DUE
        assert subscription.grace_period_ends_at is not None

    def test_invoice_paid_clears_past_due_state(self):
        client = APIClient()
        user = UserFactory(email="recovered@example.com")
        subscription = SubscriptionFactory(
            user=user, status=SubscriptionStatus.PAST_DUE, stripe_customer_id="cus_rec"
        )
        event = _event(
            "evt_paid_1", "invoice.paid", {"id": "in_rec", "customer": "cus_rec", "amount_paid": 5000, "currency": "usd"}
        )

        response = _post_event(client, event)

        assert response.status_code == 200
        subscription.refresh_from_db()
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.grace_period_ends_at is None

    def test_subscription_updated_syncs_status_and_period(self):
        client = APIClient()
        user = UserFactory(email="updated@example.com")
        subscription = SubscriptionFactory(
            user=user, status=SubscriptionStatus.ACTIVE, stripe_subscription_id="sub_upd"
        )
        event = _event(
            "evt_updated_1",
            "customer.subscription.updated",
            {
                "id": "sub_upd",
                "object": "subscription",
                "customer": subscription.stripe_customer_id,
                "status": "past_due",
                "current_period_start": 1700000000,
                "current_period_end": 1702592000,
                "cancel_at_period_end": False,
                "default_payment_method": "pm_123",
            },
        )

        response = _post_event(client, event)

        assert response.status_code == 200
        subscription.refresh_from_db()
        assert subscription.status == SubscriptionStatus.PAST_DUE
        assert subscription.default_payment_method_id == "pm_123"
        assert subscription.current_period_start is not None
        assert subscription.current_period_end is not None

    def test_subscription_deleted_marks_canceled(self):
        client = APIClient()
        user = UserFactory(email="canceled@example.com")
        subscription = SubscriptionFactory(
            user=user, status=SubscriptionStatus.ACTIVE, stripe_subscription_id="sub_del"
        )
        event = _event(
            "evt_del_1",
            "customer.subscription.deleted",
            {"id": "sub_del", "object": "subscription", "customer": subscription.stripe_customer_id},
        )

        response = _post_event(client, event)

        assert response.status_code == 200
        subscription.refresh_from_db()
        assert subscription.status == SubscriptionStatus.CANCELED
        assert subscription.canceled_at is not None

    def test_unknown_event_type_is_recorded_but_ignored(self):
        client = APIClient()
        event = _event("evt_unknown_1", "payment_intent.created", {"id": "pi_1"})

        response = _post_event(client, event)

        assert response.status_code == 200
        webhook_event = WebhookEvent.objects.get(event_id="evt_unknown_1")
        assert webhook_event.status == "processed"
