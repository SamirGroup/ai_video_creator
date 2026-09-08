"""Stateless, signed tokens for email verification and password reset.

Uses Django's `TimestampSigner`/`PasswordResetTokenGenerator` instead of a
dedicated DB table — the token is self-expiring and self-verifying, which is
enough for MVP speed without adding schema.
"""
from __future__ import annotations

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired

EMAIL_VERIFICATION_SALT = "accounts.email-verification"
EMAIL_VERIFICATION_MAX_AGE = 24 * 60 * 60  # 24 hours (FR-2)

PASSWORD_RESET_MAX_AGE = 60 * 60  # 1 hour (FR-6)


class PasswordResetTokenGeneratorWithExpiry(PasswordResetTokenGenerator):
    """Django's default generator has no built-in TTL; we enforce FR-6's 1 hour
    window by embedding+checking a timestamp ourselves via the signer below
    instead of subclassing timeout logic here.
    """


password_reset_token_generator = PasswordResetTokenGeneratorWithExpiry()


def make_email_verification_token(user_id: str) -> str:
    return signing.dumps({"user_id": str(user_id)}, salt=EMAIL_VERIFICATION_SALT)


def read_email_verification_token(token: str) -> str | None:
    """Returns the user id if valid and not expired, else None."""
    try:
        data = signing.loads(
            token,
            salt=EMAIL_VERIFICATION_SALT,
            max_age=EMAIL_VERIFICATION_MAX_AGE,
        )
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")


def make_password_reset_token(user) -> str:
    payload = {
        "user_id": str(user.pk),
        "token": password_reset_token_generator.make_token(user),
    }
    return signing.dumps(payload, salt="accounts.password-reset")


def read_password_reset_token(raw: str) -> tuple[str, str] | None:
    """Returns (user_id, inner_token) if the outer envelope is valid/unexpired."""
    try:
        data = signing.loads(
            raw, salt="accounts.password-reset", max_age=PASSWORD_RESET_MAX_AGE
        )
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id"), data.get("token")
