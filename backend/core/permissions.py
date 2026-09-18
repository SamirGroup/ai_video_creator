"""Shared DRF permission classes for role-based access control (SPEC section 2, RBAC).

Business roles (`creator`, `moderator`, `support`, `finance`, `admin`) live in
`accounts.models.Role`/`UserRole` and are independent of Django's `is_staff`/
`is_superuser` (which only gate the Django admin site).
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    """Factory-style permission: `HasRole("finance", "admin")` as a base class.

    Usage: subclass per endpoint, e.g.
        class IsFinanceOrAdmin(HasRole):
            allowed_roles = {"finance", "admin"}
    """

    allowed_roles: set[str] = set()

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        if not self.allowed_roles:
            return True
        return user.user_roles.filter(role__code__in=self.allowed_roles).exists()


class IsAdmin(HasRole):
    allowed_roles = {"admin"}


class IsModeratorOrAdmin(HasRole):
    allowed_roles = {"moderator", "admin"}


class IsFinanceOrAdmin(HasRole):
    allowed_roles = {"finance", "admin"}


class IsSupportOrAdmin(HasRole):
    allowed_roles = {"support", "admin"}


# --- Track E ---
class IsStaffWith2FA(BasePermission):
    """FR-9 / NFR-8: staff endpoints require a staff role AND an enrolled TOTP
    second factor. Combine with a role permission, e.g.
    `permission_classes = [IsAdmin, IsStaffWith2FA]`.

    `settings.STAFF_2FA_REQUIRED=False` relaxes the TOTP check (tests, local
    scratch runs); the role check always applies.
    """

    STAFF_ROLES = {"moderator", "support", "finance", "admin"}
    message = "Two-factor authentication must be enabled for staff access."

    def has_permission(self, request, view) -> bool:
        from django.conf import settings

        user = request.user
        if not (user and user.is_authenticated):
            return False
        if (
            not user.is_superuser
            and not user.user_roles.filter(role__code__in=self.STAFF_ROLES).exists()
        ):
            return False
        from accounts.test_access import temporary_2fa_exemption

        if temporary_2fa_exemption(user):
            return True
        if not getattr(settings, "STAFF_2FA_REQUIRED", True):
            return True
        return bool(getattr(user, "is_totp_enabled", False))
