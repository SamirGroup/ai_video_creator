"""TOTP two-factor authentication for staff accounts (FR-9, NFR-8).

RFC 6238 / RFC 4226 implemented with the standard library only (`hmac`,
`hashlib`, `base64`, `struct`, `secrets`) — no `pyotp` dependency:

* 30-second time step, 6 digits, HMAC-SHA1 (what Google Authenticator, Authy,
  1Password etc. expect from an `otpauth://` URI without explicit parameters);
* verification accepts +-1 step of clock drift and refuses to accept the same
  time step twice (replay guard, kept in the cache);
* the secret is 160 random bits, base32-encoded for the QR code and stored
  encrypted at rest in `users.totp_secret_enc` (NFR-2).

Login contract (see `LoginView`): when a user who has TOTP enabled — or who
holds a staff role while `STAFF_2FA_REQUIRED` is on — authenticates with a
password/Google, the API does NOT issue JWTs. It returns

    {"requires_2fa": true, "challenge_token": "<signed, 5 min>",
     "setup_required": <bool>}

and the client completes the login with `POST /auth/2fa/login`
(`{challenge_token, code}`), or — when `setup_required` is true — enrols first
via `POST /auth/2fa/enable` + `POST /auth/2fa/verify` passing the same
`challenge_token`. `verify` then returns the JWTs, so a staff account never
holds a session without a second factor.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
import struct
import time
from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from accounts.models import User

logger = logging.getLogger("accounts.twofactor")

TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6
TOTP_WINDOW = 1  # accept +-1 step (RFC 6238 section 5.2 recommends at most one)
TOTP_SECRET_BYTES = 20  # 160 bits, RFC 4226 section 4 minimum

CHALLENGE_SALT = "accounts.2fa-challenge"
CHALLENGE_MAX_AGE = 5 * 60  # seconds

STAFF_ROLES = ("moderator", "support", "finance", "admin")

_CODE_RE = re.compile(r"^\d{6,8}$")


# ---------------------------------------------------------------------------
# RFC 4226 / RFC 6238 primitives
# ---------------------------------------------------------------------------
def generate_secret() -> str:
    """New base32 secret (no padding) suitable for an authenticator app."""
    return (
        base64.b32encode(secrets.token_bytes(TOTP_SECRET_BYTES))
        .decode("ascii")
        .rstrip("=")
    )


def _decode_secret(secret: str | bytes) -> bytes:
    if isinstance(secret, bytes):
        return secret
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * (-len(normalized) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def hotp(
    secret: str | bytes,
    counter: int,
    digits: int = TOTP_DIGITS,
    algorithm: str = "sha1",
) -> str:
    """RFC 4226 HOTP value for `counter`. `secret` is base32 text or raw bytes."""
    key = _decode_secret(secret)
    message = struct.pack(">Q", counter)
    digest = hmac.new(key, message, getattr(hashlib, algorithm)).digest()
    offset = digest[-1] & 0x0F
    binary = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    return str(binary % (10**digits)).zfill(digits)


def totp_counter(timestamp: float | None = None, step: int = TOTP_STEP_SECONDS) -> int:
    now = time.time() if timestamp is None else timestamp
    return int(now // step)


def totp(
    secret: str | bytes,
    timestamp: float | None = None,
    *,
    step: int = TOTP_STEP_SECONDS,
    digits: int = TOTP_DIGITS,
    algorithm: str = "sha1",
) -> str:
    """RFC 6238 TOTP value at `timestamp` (defaults to now)."""
    return hotp(
        secret, totp_counter(timestamp, step), digits=digits, algorithm=algorithm
    )


def verify_totp(
    secret: str | bytes,
    code: str,
    *,
    timestamp: float | None = None,
    window: int = TOTP_WINDOW,
    step: int = TOTP_STEP_SECONDS,
    digits: int = TOTP_DIGITS,
) -> int | None:
    """Return the matching counter when `code` is valid within +-`window`
    steps, else None. Comparison is constant-time; every candidate is checked
    so timing does not reveal which step matched.
    """
    code = (code or "").strip().replace(" ", "")
    if not _CODE_RE.match(code) or len(code) != digits:
        return None
    base = totp_counter(timestamp, step)
    matched: int | None = None
    for delta in range(-window, window + 1):
        counter = base + delta
        if hmac.compare_digest(hotp(secret, counter, digits=digits), code):
            matched = counter
    return matched


def otpauth_uri(secret: str, account_name: str, issuer: str | None = None) -> str:
    """`otpauth://totp/...` URI the client renders as a QR code."""
    issuer = issuer or getattr(settings, "TOTP_ISSUER", "AI YouTube Content Ecosystem")
    label = quote(f"{issuer}:{account_name}", safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_STEP_SECONDS}"
    )


# ---------------------------------------------------------------------------
# Account-level helpers
# ---------------------------------------------------------------------------
def _replay_key(user_id, counter: int) -> str:
    return f"2fa:used:{user_id}:{counter}"


def verify_user_code(user: User, code: str) -> bool:
    """Validate `code` against the user's stored secret with replay protection:
    a given (user, time-step) pair is accepted exactly once.
    """
    secret = user.totp_secret_enc
    if not secret:
        return False
    counter = verify_totp(secret, code)
    if counter is None:
        return False
    # cache.add is atomic on Redis/locmem: False means this step was already consumed.
    if not cache.add(
        _replay_key(user.pk, counter),
        "1",
        timeout=TOTP_STEP_SECONDS * (2 * TOTP_WINDOW + 2),
    ):
        logger.warning("totp_replay_rejected", extra={"user_id": str(user.pk)})
        return False
    return True


def is_staff_user(user: User) -> bool:
    return (
        user.is_superuser or user.user_roles.filter(role__code__in=STAFF_ROLES).exists()
    )


def requires_2fa_for_login(user: User) -> bool:
    """FR-9: staff always (while STAFF_2FA_REQUIRED), any user who enrolled."""
    if user.is_superuser or user.is_totp_enabled:
        return True
    return bool(getattr(settings, "STAFF_2FA_REQUIRED", True)) and is_staff_user(user)


def issue_challenge(user: User) -> str:
    """Short-lived, single-use signed token proving the first factor succeeded."""
    return signing.dumps(
        {
            "user_id": str(user.pk),
            "nonce": secrets.token_urlsafe(16),
            "purpose": "2fa_login",
        },
        salt=CHALLENGE_SALT,
    )


def consume_challenge(token: str) -> User | None:
    """Resolve a challenge token to its user, or None when invalid/expired/used."""
    try:
        data = signing.loads(token, salt=CHALLENGE_SALT, max_age=CHALLENGE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if data.get("purpose") != "2fa_login":
        return None
    user = User.objects.filter(pk=data.get("user_id")).first()
    if user is None or not user.is_active:
        return None
    return user


def mark_challenge_used(token: str) -> bool:
    """Single-use guard. Returns False when the nonce was already consumed."""
    try:
        data = signing.loads(token, salt=CHALLENGE_SALT, max_age=CHALLENGE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return cache.add(
        f"2fa:challenge:{data.get('nonce')}", "1", timeout=CHALLENGE_MAX_AGE + 60
    )


def two_factor_challenge_response(user: User) -> Response:
    """Body returned by the login endpoints instead of JWTs (see module doc)."""
    return Response(
        {
            "requires_2fa": True,
            "challenge_token": issue_challenge(user),
            "setup_required": not user.is_totp_enabled,
        },
        status=status.HTTP_200_OK,
    )


def _issue_tokens(user: User, request):
    # Imported lazily: accounts.views imports this module for the login gate.
    from accounts.views import _issue_tokens_response

    user.last_login_at = timezone.now()
    user.save(update_fields=["last_login_at", "updated_at"])
    return _issue_tokens_response(user, request=request)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
class TwoFactorThrottle(AnonRateThrottle):
    scope = "two_factor"


class _ChallengeOrAuthMixin:
    """Resolve the acting user either from the Bearer JWT or from a login
    `challenge_token` (so staff can enrol before their first session exists).
    """

    def _resolve_user(self, request) -> tuple[User | None, str | None]:
        if request.user and request.user.is_authenticated:
            return request.user, None
        token = (
            request.data.get("challenge_token")
            if isinstance(request.data, dict)
            else None
        )
        if token:
            user = consume_challenge(token)
            if user is not None:
                return user, token
        return None, None


class TwoFactorEnableView(_ChallengeOrAuthMixin, APIView):
    """POST /api/v1/auth/2fa/enable — start enrolment.

    Generates a new secret, stores it (encrypted) as *pending* and returns the
    base32 secret + otpauth URI. `is_totp_enabled` stays False until `verify`.
    """

    permission_classes = [AllowAny]
    throttle_classes = [TwoFactorThrottle]

    def post(self, request):
        user, _ = self._resolve_user(request)
        if user is None:
            return Response(
                {"detail": "Authentication credentials were not provided."}, status=401
            )
        if user.is_totp_enabled:
            return Response(
                {"detail": "Two-factor authentication is already enabled."},
                status=status.HTTP_409_CONFLICT,
            )
        secret = generate_secret()
        user.totp_secret_enc = secret
        user.save(update_fields=["totp_secret_enc", "updated_at"])
        logger.info("totp_enrolment_started", extra={"user_id": str(user.pk)})
        return Response(
            {"secret": secret, "otpauth_uri": otpauth_uri(secret, user.email)}
        )


class TwoFactorCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=16)
    challenge_token = serializers.CharField(required=False, allow_blank=True)


class TwoFactorVerifyView(_ChallengeOrAuthMixin, APIView):
    """POST /api/v1/auth/2fa/verify — confirm enrolment with a live code.

    Activates TOTP, notifies the user (mandatory security notification) and
    writes an audit row. When the call was authenticated with a login
    `challenge_token`, the response also carries the JWTs (login completes).
    """

    permission_classes = [AllowAny]
    throttle_classes = [TwoFactorThrottle]

    def post(self, request):
        serializer = TwoFactorCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, challenge = self._resolve_user(request)
        if user is None:
            return Response(
                {"detail": "Authentication credentials were not provided."}, status=401
            )
        if user.is_totp_enabled:
            return Response(
                {"detail": "Two-factor authentication is already enabled."},
                status=status.HTTP_409_CONFLICT,
            )
        if not user.totp_secret_enc:
            return Response(
                {"detail": "Call /auth/2fa/enable first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not verify_user_code(user, serializer.validated_data["code"]):
            return Response(
                {"detail": "Invalid verification code."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if challenge and not mark_challenge_used(challenge):
            return Response(
                {"detail": "Challenge token already used."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_totp_enabled = True
        user.save(update_fields=["is_totp_enabled", "updated_at"])

        from audit.services import record_audit_event
        from notifications.services import notify

        record_audit_event(
            actor_type="user",
            actor_id=user.pk,
            action="auth.2fa_enabled",
            resource_type="user",
            resource_id=str(user.pk),
            request=request,
        )
        notify(user, "auth.2fa_enabled")
        logger.info("totp_enabled", extra={"user_id": str(user.pk)})

        if challenge:
            return _issue_tokens(user, request)
        return Response(
            {"detail": "Two-factor authentication enabled.", "is_totp_enabled": True}
        )


class TwoFactorLoginSerializer(serializers.Serializer):
    challenge_token = serializers.CharField()
    code = serializers.CharField(max_length=16)


class TwoFactorLoginView(APIView):
    """POST /api/v1/auth/2fa/login — second step of the login (FR-9).

    `{challenge_token, code}` -> `{access, user}` + refresh cookie, exactly like
    a successful `POST /auth/login` for a non-2FA account.
    """

    permission_classes = [AllowAny]
    throttle_classes = [TwoFactorThrottle]

    def post(self, request):
        serializer = TwoFactorLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data["challenge_token"]

        user = consume_challenge(token)
        if user is None:
            return Response(
                {"detail": "Invalid or expired challenge token."}, status=401
            )
        if not user.is_totp_enabled:
            return Response(
                {
                    "detail": "Two-factor authentication is not set up. Enrol via /auth/2fa/enable.",
                    "setup_required": True,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if not verify_user_code(user, serializer.validated_data["code"]):
            logger.warning("totp_login_code_rejected", extra={"user_id": str(user.pk)})
            return Response({"detail": "Invalid verification code."}, status=401)
        if not mark_challenge_used(token):
            return Response({"detail": "Challenge token already used."}, status=401)

        logger.info("user_logged_in_2fa", extra={"user_id": str(user.pk)})
        return _issue_tokens(user, request)
