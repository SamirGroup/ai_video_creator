"""Recover orphaned planning reservations and reconcile out-of-order refunds."""

from datetime import timedelta
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from billing.models import AIWalletHold, WebhookEvent
from billing.wallet import release_operation, reverse_stripe_refund


@shared_task(name="billing.reconcile_ai_wallets")
def reconcile_ai_wallets():
    from content_planning.models import ContentPlan

    released = 0
    for hold in AIWalletHold.objects.filter(
        released=False, created_at__lt=timezone.now() - timedelta(hours=2)
    ):
        if not hold.reference.startswith("content-plan:"):
            continue
        with transaction.atomic():
            plan_id = hold.reference.split(":", 1)[1]
            ContentPlan.objects.filter(pk=plan_id, status="generating").update(
                status="failed", error_code="worker_timeout"
            )
            release_operation(hold.reference)
            released += 1
    for event in WebhookEvent.objects.filter(
        event_type="charge.refunded", status="processed"
    ):
        payload = event.payload
        charge = payload.get("data", {}).get("object", {})
        if charge.get("id"):
            reverse_stripe_refund(charge)
    return {"released_holds": released}
