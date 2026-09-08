"""Transactional email sending for auth flows (FR-2, FR-6, FR-74).

MVP uses Django's synchronous `send_mail` with the console backend in dev
(see settings). Moving these behind a Celery task is a straightforward
follow-up once the notification pipeline (notifications app) lands — flagged
here rather than silently left half-done.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("accounts.emails")


def send_verification_email(*, to_email: str, token: str) -> None:
    verify_url = f"{settings.FRONTEND_BASE_URL}/verify-email?token={token}"
    send_mail(
        subject="Confirm your email — AI YouTube Content Ecosystem",
        message=f"Confirm your email address: {verify_url}\nThis link expires in 24 hours.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )
    logger.info("verification_email_sent", extra={"to_email_domain": to_email.split("@")[-1]})


def send_password_reset_email(*, to_email: str, token: str) -> None:
    reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?token={token}"
    send_mail(
        subject="Reset your password — AI YouTube Content Ecosystem",
        message=f"Reset your password: {reset_url}\nThis link expires in 1 hour.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )
    logger.info("password_reset_email_sent", extra={"to_email_domain": to_email.split("@")[-1]})
