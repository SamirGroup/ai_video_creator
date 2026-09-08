"""Notification fan-out (FR-74..FR-77).

`notify(user, type, ctx)` is the single entry point every other app uses:

    from notifications.services import notify
    notify(user, "video.awaiting_approval", job=job, ctx={"title": job.title, "url": ...})

It:
1. renders subject/body in the user's locale (en/ru/uz) from `templates_registry`;
2. writes an `in_app` Notification row (always, unless the user disabled the
   type and the type is not mandatory);
3. writes an `email` Notification row and queues `send_notification_email`
   (Celery) after the surrounding transaction commits — so a rolled-back job
   never emails anyone.

Transactional/security types (`MANDATORY_TYPES`) ignore preferences (FR-76).
"""
from __future__ import annotations

import logging

from django.db import transaction

from notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationStatus,
)
from notifications.templates_registry import MANDATORY_TYPES, render

logger = logging.getLogger("notifications.services")


def _preference(user, type_: str) -> NotificationPreference | None:
    return NotificationPreference.objects.filter(user=user, type=type_).first()


def _channel_enabled(user, type_: str, channel: str) -> bool:
    if type_ in MANDATORY_TYPES:
        return True
    pref = _preference(user, type_)
    if pref is None:
        return True  # default ON (FR-76)
    return {
        NotificationChannel.EMAIL: pref.email_enabled,
        NotificationChannel.IN_APP: pref.in_app_enabled,
        NotificationChannel.PUSH: pref.push_enabled,
    }.get(channel, False)


def notify(
    user,
    type_: str,
    *,
    ctx: dict | None = None,
    job=None,
    payload: dict | None = None,
    channels: tuple[str, ...] = (NotificationChannel.IN_APP, NotificationChannel.EMAIL),
    locale: str | None = None,
) -> list[Notification]:
    """Create + dispatch notifications for `user`. Returns the rows created.

    Never raises for a delivery problem — the business action that triggered
    the notification must not fail because email is down (NFR-28).
    """
    ctx = ctx or {}
    locale = locale or getattr(user, "locale", "en") or "en"
    subject, body = render(type_, locale, ctx)
    created: list[Notification] = []

    for channel in channels:
        if not _channel_enabled(user, type_, channel):
            continue
        row = Notification.objects.create(
            user=user,
            type=type_,
            channel=channel,
            title=subject,
            body=body,
            payload=payload or {},
            related_job=job,
            status=NotificationStatus.SENT if channel == NotificationChannel.IN_APP else NotificationStatus.QUEUED,
        )
        if channel == NotificationChannel.IN_APP:
            from django.utils import timezone

            row.sent_at = timezone.now()
            row.save(update_fields=["sent_at"])
        created.append(row)

        if channel == NotificationChannel.EMAIL:
            from notifications.tasks import send_notification_email

            notification_id = str(row.id)
            transaction.on_commit(lambda nid=notification_id: send_notification_email.delay(nid))

    logger.info(
        "notification_created",
        extra={"user_id": str(user.id), "type": type_, "channels": [n.channel for n in created]},
    )
    return created


def notify_admins(type_: str, *, ctx: dict | None = None, job=None, payload: dict | None = None) -> None:
    """Admin alert helper (FR-44, FR-52, FR-58): fan out to every user holding
    the `admin` role. In-app + email.
    """
    from accounts.models import User

    admins = User.objects.filter(user_roles__role__code="admin").distinct()
    for admin in admins:
        notify(admin, type_, ctx=ctx, job=job, payload=payload)
