"""Celery tasks for notification delivery (FR-74, FR-77)."""
from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from notifications.models import Notification, NotificationChannel, NotificationStatus

logger = logging.getLogger("notifications.tasks")


@shared_task(
    name="notifications.send_notification_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def send_notification_email(self, notification_id: str) -> bool:
    """Sends one queued email Notification. Idempotent: an already-sent row is a no-op."""
    row = Notification.objects.select_related("user").filter(id=notification_id).first()
    if row is None or row.channel != NotificationChannel.EMAIL:
        return False
    if row.status in (NotificationStatus.SENT, NotificationStatus.READ):
        return True
    try:
        send_mail(
            subject=row.title,
            message=row.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[row.user.email],
            fail_silently=False,
        )
    except Exception as exc:  # noqa: BLE001
        row.status = NotificationStatus.FAILED
        row.error = str(exc)[:2000]
        row.save(update_fields=["status", "error"])
        logger.warning("notification_email_failed", extra={"notification_id": notification_id})
        raise self.retry(exc=exc)
    row.status = NotificationStatus.SENT
    row.sent_at = timezone.now()
    row.error = ""
    row.save(update_fields=["status", "sent_at", "error"])
    return True
