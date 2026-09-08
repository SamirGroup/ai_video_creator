"""Refresh-token cookie helpers (FR-4: httpOnly + Secure + SameSite=Lax cookie)."""
from __future__ import annotations

from django.conf import settings
from rest_framework.response import Response

REFRESH_COOKIE_NAME = "refresh_token"


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        str(refresh_token),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="Lax",
        path="/api/v1/auth/",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth/")
