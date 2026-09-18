from urllib.parse import urlsplit
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from audit.services import record_audit_event
from telegram_integration.views import IsSuperAdmin
from .models import AuthLogo


class AuthLogoSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthLogo
        fields = ["id", "name", "image_url", "link_url", "sort_order", "is_active"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        for field in ("image_url", "link_url"):
            if field in attrs:
                url = urlsplit(attrs[field])
                if (
                    url.scheme != "https"
                    or not url.hostname
                    or url.username
                    or url.password
                ):
                    raise serializers.ValidationError(
                        {field: "Use a public HTTPS URL without credentials."}
                    )
        return attrs


class PublicAuthLogos(generics.ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = AuthLogoSerializer
    pagination_class = None
    queryset = AuthLogo.objects.filter(is_active=True)


class AuditLogoMixin:
    permission_classes = [IsSuperAdmin]
    serializer_class = AuthLogoSerializer
    queryset = AuthLogo.objects.all()

    def audit(self, obj, action):
        record_audit_event(
            actor_type="user",
            actor_id=self.request.user.pk,
            action=action,
            resource_type="auth_logo",
            resource_id=str(obj.pk),
            request=self.request,
            metadata={"name": obj.name},
        )

    def perform_create(self, serializer):
        self.audit(serializer.save(), "auth_logo.created")

    def perform_update(self, serializer):
        self.audit(serializer.save(), "auth_logo.updated")

    def perform_destroy(self, instance):
        self.audit(instance, "auth_logo.deleted")
        instance.delete()


class AdminAuthLogos(AuditLogoMixin, generics.ListCreateAPIView):
    pagination_class = None


class AdminAuthLogoDetail(AuditLogoMixin, generics.RetrieveUpdateDestroyAPIView):
    pass
