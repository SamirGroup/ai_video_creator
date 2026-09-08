"""Active session listing / revocation (FR-5): `GET /me/sessions`,
`DELETE /me/sessions/{id}`.

A "session" is one refresh-token lineage. simplejwt rotates the refresh jti
on every `/auth/refresh`, so the stable identifier is the `sid` claim we add
at login (`record_session`) which rotation copies verbatim. Listing joins the
non-blacklisted, unexpired `OutstandingToken` rows of the user to their
`SessionMeta` (user agent / IP captured at login). Revoking blacklists every
outstanding token carrying that `sid`, which also invalidates the access
tokens' refresh path (access tokens themselves expire within 15 minutes).
"""
from __future__ import annotations

import logging

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.cookies import REFRESH_COOKIE_NAME, clear_refresh_cookie
from accounts.models import SessionMeta, User

logger = logging.getLogger("accounts.sessions")

SID_CLAIM = "sid"


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45] or None
    return request.META.get("REMOTE_ADDR") or None


def record_session(user: User, refresh: RefreshToken, request) -> SessionMeta:
    """Create the `SessionMeta` row for a fresh refresh token and stamp its id
    into the token as `sid`. Called from `accounts.views._issue_tokens_response`.
    """
    meta = SessionMeta.objects.create(
        user=user,
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:1000],
        ip_address=_client_ip(request),
        last_seen_at=timezone.now(),
    )
    refresh[SID_CLAIM] = str(meta.id)
    # `RefreshToken.for_user` already stored the token text without `sid`;
    # keep the outstanding row in sync so listing can read the claim back.
    OutstandingToken.objects.filter(jti=refresh["jti"]).update(token=str(refresh))
    return meta


def _sid_of(outstanding: OutstandingToken) -> str | None:
    try:
        payload = RefreshToken(outstanding.token, verify=False).payload
    except TokenError:
        return None
    return payload.get(SID_CLAIM)


def active_outstanding_tokens(user: User):
    return OutstandingToken.objects.filter(
        user=user, expires_at__gt=timezone.now(), blacklistedtoken__isnull=True
    ).order_by("-created_at")


def list_sessions(user: User) -> list[dict]:
    tokens_by_sid: dict[str, OutstandingToken] = {}
    for outstanding in active_outstanding_tokens(user):
        sid = _sid_of(outstanding)
        if sid and sid not in tokens_by_sid:
            tokens_by_sid[sid] = outstanding
    if not tokens_by_sid:
        return []
    metas = {
        str(m.id): m
        for m in SessionMeta.objects.filter(user=user, id__in=list(tokens_by_sid), revoked_at__isnull=True)
    }
    sessions = []
    for sid, outstanding in tokens_by_sid.items():
        meta = metas.get(sid)
        if meta is None:
            continue
        sessions.append(
            {
                "id": sid,
                "created_at": meta.created_at,
                "last_seen_at": meta.last_seen_at,
                "expires_at": outstanding.expires_at,
                "user_agent": meta.user_agent,
                "ip_address": meta.ip_address,
            }
        )
    sessions.sort(key=lambda s: s["created_at"], reverse=True)
    return sessions


def revoke_session(user: User, session_id) -> bool:
    """Blacklist every live refresh token of the session. Returns False when
    the session does not belong to the user or is already gone (no IDOR:
    the lookup is always user-scoped).
    """
    meta = SessionMeta.objects.filter(user=user, id=session_id).first()
    if meta is None:
        return False
    revoked = 0
    for outstanding in active_outstanding_tokens(user):
        if _sid_of(outstanding) == str(meta.id):
            BlacklistedToken.objects.get_or_create(token=outstanding)
            revoked += 1
    if meta.revoked_at is None:
        meta.revoked_at = timezone.now()
        meta.save(update_fields=["revoked_at"])
    logger.info("session_revoked", extra={"user_id": str(user.pk), "session_id": str(meta.id), "tokens": revoked})
    return True


def revoke_all_sessions(user: User) -> int:
    """Blacklist all live refresh tokens (admin suspend, account deletion)."""
    count = 0
    for outstanding in active_outstanding_tokens(user):
        BlacklistedToken.objects.get_or_create(token=outstanding)
        count += 1
    SessionMeta.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())
    return count


def current_session_id(request) -> str | None:
    """`sid` of the caller's current session: from the access token claim, or
    the refresh cookie as a fallback.
    """
    auth = getattr(request, "auth", None)
    if auth is not None:
        try:
            sid = auth.get(SID_CLAIM)
        except Exception:
            sid = None
        if sid:
            return str(sid)
    raw = request.COOKIES.get(REFRESH_COOKIE_NAME)
    if raw:
        try:
            return RefreshToken(raw, verify=False).payload.get(SID_CLAIM)
        except TokenError:
            return None
    return None


class SessionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    last_seen_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField()
    user_agent = serializers.CharField(allow_blank=True)
    ip_address = serializers.CharField(allow_null=True)
    is_current = serializers.BooleanField()


class SessionListView(APIView):
    """GET /api/v1/me/sessions."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        current = current_session_id(request)
        rows = [{**s, "is_current": s["id"] == current} for s in list_sessions(request.user)]
        return Response({"results": SessionSerializer(rows, many=True).data})


class SessionDetailView(APIView):
    """DELETE /api/v1/me/sessions/{id} — revoke one device."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id):
        if not revoke_session(request.user, session_id):
            return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        if current_session_id(request) == str(session_id):
            clear_refresh_cookie(response)
        return response
