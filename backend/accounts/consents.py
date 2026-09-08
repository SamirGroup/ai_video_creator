"""Consent ledger (SPEC 5.28 `consents`, FR-30, GDPR-style evidence).

    from accounts.consents import record_consent
    record_consent(user, ConsentType.REVENUE_SHARE, True, scope_details={...}, request=request)

Every call appends a row (never updates): granting again after a revocation
is a new row, and `granted=False` writes a row with `revoked_at` set. The
`channels` OAuth flow and the contract-signing flow are the producers; this
module also hosts the `GET /me/consents` view so `accounts/views.py` (owned by
another track) stays untouched.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from accounts.models import Consent


class ConsentType(models.TextChoices):
    OAUTH_YOUTUBE = "oauth_youtube", "YouTube OAuth"
    OAUTH_ADSENSE = "oauth_adsense", "AdSense OAuth"
    DATA_PROCESSING = "data_processing", "Data processing / AI"
    MARKETING = "marketing", "Marketing emails"
    REVENUE_SHARE = "revenue_share", "Revenue share terms"
    PUBLISH_TO_CHANNEL = "publish_to_channel", "Publish to channel"


def record_consent(user, consent_type: str, granted: bool, scope_details: dict | None = None, request=None) -> Consent:
    ip_address = None
    user_agent = ""
    if request is not None:
        ip_address = request.META.get("REMOTE_ADDR") or None
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:2000]
    now = timezone.now()
    return Consent.objects.create(
        user=user,
        consent_type=consent_type,
        granted=granted,
        scope_details=scope_details or {},
        granted_at=now,
        revoked_at=None if granted else now,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def latest_consent(user, consent_type: str) -> Consent | None:
    return Consent.objects.filter(user=user, consent_type=consent_type).order_by("-granted_at").first()


def has_consent(user, consent_type: str) -> bool:
    latest = latest_consent(user, consent_type)
    return bool(latest and latest.granted and latest.revoked_at is None)


class ConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consent
        fields = ["id", "consent_type", "granted", "scope_details", "granted_at", "revoked_at"]
        read_only_fields = fields


class MyConsentsView(ListAPIView):
    """GET /api/v1/me/consents — full consent history, newest first (no IP/UA exposed)."""

    permission_classes = [IsAuthenticated]
    serializer_class = ConsentSerializer
    pagination_class = None

    def get_queryset(self):
        return Consent.objects.filter(user=self.request.user).order_by("-granted_at")
