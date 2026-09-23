"""Advertising partners: explicit admin-managed links, never inferred endorsements."""

import ipaddress
from urllib.parse import urlsplit

from audit.services import record_audit_event
from core.permissions import IsAdmin, IsStaffWith2FA
from django.db import transaction
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from adminpanel.models import Partner, PartnerBanner


def public_https(value):
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or hostname == "localhost"
        or hostname.endswith((".localhost", ".local", ".internal"))
    ):
        raise serializers.ValidationError("Use a public HTTPS URL without credentials.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if "." not in hostname:
            raise serializers.ValidationError("Use a public HTTPS hostname.") from None
    else:
        if not address.is_global:
            raise serializers.ValidationError(
                "Private network addresses are not allowed."
            )
    return value


class PartnerSerializer(serializers.ModelSerializer):
    image_url = serializers.URLField(max_length=2000, validators=[public_https])
    link_url = serializers.URLField(max_length=2000, validators=[public_https])

    class Meta:
        model = Partner
        fields = (
            "id",
            "name",
            "image_url",
            "link_url",
            "caption",
            "sort_order",
            "is_active",
            "is_affiliate",
        )
        read_only_fields = ("id",)


class BannerSerializer(serializers.ModelSerializer):
    animation_seconds = serializers.IntegerField(min_value=15, max_value=120)

    class Meta:
        model = PartnerBanner
        fields = (
            "enabled",
            "title",
            "subtitle",
            "animation_enabled",
            "animation_seconds",
        )


def audit(request, obj, action):
    record_audit_event(
        actor_type="staff",
        actor_id=request.user.pk,
        action=action,
        resource_type="partner_banner" if isinstance(obj, PartnerBanner) else "partner",
        resource_id=str(obj.pk),
        request=request,
        metadata={"name": getattr(obj, "name", "banner")},
    )


class PartnerAdminMixin:
    permission_classes = (IsAdmin, IsStaffWith2FA)
    serializer_class = PartnerSerializer
    queryset = Partner.objects.all()

    @transaction.atomic
    def perform_create(self, serializer):
        audit(self.request, serializer.save(), "partner.created")

    @transaction.atomic
    def perform_update(self, serializer):
        audit(self.request, serializer.save(), "partner.updated")

    @transaction.atomic
    def perform_destroy(self, instance):
        audit(self.request, instance, "partner.deleted")
        instance.delete()


class AdminPartners(PartnerAdminMixin, generics.ListCreateAPIView):
    pagination_class = None


class AdminPartnerDetail(PartnerAdminMixin, generics.RetrieveUpdateDestroyAPIView):
    pass


class AdminPartnerBanner(generics.RetrieveUpdateAPIView):
    permission_classes = (IsAdmin, IsStaffWith2FA)
    serializer_class = BannerSerializer
    http_method_names = ("get", "patch", "head", "options")

    def get_object(self):
        return PartnerBanner.objects.get_or_create(pk=1)[0]

    @transaction.atomic
    def perform_update(self, serializer):
        audit(self.request, serializer.save(), "partner_banner.updated")


class PublicPartners(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        banner = PartnerBanner.objects.filter(pk=1).first() or PartnerBanner()
        partners = Partner.objects.filter(is_active=True) if banner.enabled else []
        return Response(
            {
                "banner": BannerSerializer(banner).data,
                "partners": PartnerSerializer(partners, many=True).data,
            },
            headers={"Cache-Control": "no-store"},
        )
