"""SPEC 5.1 `users`, 5.2 `roles`/`user_roles`."""

from __future__ import annotations

import uuid

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from accounts.managers import UserManager
from core.fields import EncryptedTextField
from core.models import TimestampedModel
from core.languages import DEFAULT_LANGUAGE, LANGUAGE_CHOICES


class UserStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    PENDING_DELETION = "pending_deletion", "Pending deletion"
    DELETED = "deleted", "Deleted"


class Locale(models.TextChoices):
    EN = "en", "English"
    RU = "ru", "Russian"
    UZ = "uz", "Uzbek"


class User(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    """Platform account. Extends TimestampedModel (UUID pk + timestamps) instead
    of Django's default integer-pk user table, per SPEC 5 conventions.
    """

    # SPEC 5.1 calls for CITEXT (case-insensitive unique email); Django 5.2 removed
    # `django.contrib.postgres.fields.CITextField` for use outside historical
    # migrations. We get equivalent behavior without a Postgres extension by
    # always normalizing to lowercase before it reaches this field (see
    # UserManager.normalize_email usage and the register/login serializers).
    email = models.EmailField(unique=True)
    # Django's password-hashing machinery (set_password/check_password) operates
    # on the `password` attribute name; only the DB column is renamed to match
    # SPEC 5.1's `password_hash`. NULL for Google-only accounts (FR-3).
    password = models.CharField(
        max_length=255, null=True, blank=True, db_column="password_hash"
    )
    full_name = models.CharField(max_length=255, blank=True, default="")
    is_email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    google_sub = models.CharField(max_length=255, unique=True, null=True, blank=True)
    locale = models.CharField(
        max_length=10, choices=LANGUAGE_CHOICES, default=DEFAULT_LANGUAGE
    )
    timezone = models.CharField(max_length=64, default="UTC")
    status = models.CharField(
        max_length=20, choices=UserStatus.choices, default=UserStatus.ACTIVE
    )
    totp_secret_enc = EncryptedTextField(null=True, blank=True)
    is_totp_enabled = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)
    marketing_opt_in = models.BooleanField(default=False)

    # Django admin site access only — distinct from business RBAC (Role/UserRole below).
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"], name="ix_users_email"),
            models.Index(fields=["google_sub"], name="ix_users_google_sub"),
            models.Index(fields=["status"], name="ix_users_status"),
        ]

    def __str__(self) -> str:
        return self.email

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    def has_role(self, *role_codes: str) -> bool:
        return self.user_roles.filter(role__code__in=role_codes).exists()


class Role(models.Model):
    """Business RBAC role (SPEC 5.2): creator, moderator, support, finance, admin."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "roles"

    def __str__(self) -> str:
        return self.code


class UserRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_roles",
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_roles"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uq_user_role")
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.role_id}"


# --- Track A ---------------------------------------------------------------
class Consent(models.Model):
    """SPEC 5.28 `consents`: append-only evidence of each granular consent
    (FR-30) and OAuth grant. Helpers live in `accounts.consents`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    consent_type = models.CharField(max_length=64)
    granted = models.BooleanField()
    scope_details = models.JSONField(default=dict, blank=True)
    granted_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    class Meta:
        db_table = "consents"
        indexes = [
            models.Index(
                fields=["user", "consent_type", "granted_at"],
                name="ix_consents_user_type_at",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.consent_type}:{'granted' if self.granted else 'revoked'}"


# --- Track E ---------------------------------------------------------------
class SessionMeta(models.Model):
    """FR-5 device metadata for `GET /me/sessions`.

    simplejwt's `OutstandingToken` knows jti/expiry but not where a refresh
    token was issued. Each login creates one row; its UUID is embedded in the
    refresh token as the `sid` claim and survives rotation, so the session id
    shown to the user is stable while the jti changes every refresh.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="session_meta"
    )
    user_agent = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "session_meta"
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="ix_session_meta_user")
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.id}"


class DataRequestKind(models.TextChoices):
    EXPORT = "export", "Export"
    DELETION = "deletion", "Deletion"


class DataRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    REJECTED = "rejected", "Rejected"
    CANCELED = "canceled", "Canceled"
    FAILED = "failed", "Failed"


class DataRequest(models.Model):
    """SPEC 5.29 `data_requests` (FR-86, FR-87). `scheduled_for` is the
    anonymisation due date for deletion requests (requested_at + 30 days);
    export zips live at `export_s3_key` until `export_expires_at`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="data_requests"
    )
    kind = models.CharField(max_length=10, choices=DataRequestKind.choices)
    status = models.CharField(
        max_length=12,
        choices=DataRequestStatus.choices,
        default=DataRequestStatus.PENDING,
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    export_s3_key = models.TextField(blank=True, default="")
    export_expires_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    processed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "data_requests"
        indexes = [
            models.Index(
                fields=["user", "kind", "status"], name="ix_data_requests_user_kind"
            ),
            models.Index(
                fields=["kind", "status", "scheduled_for"], name="ix_data_requests_due"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.kind}:{self.status}"
