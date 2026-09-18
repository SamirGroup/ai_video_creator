from __future__ import annotations
from accounts.test_access import temporary_2fa_exemption

from rest_framework import serializers

from accounts.models import Role, User
from billing.models import Plan
from providers.models import ApiCredentialConfig
from video_pipeline.models import VideoJob


class AdminUserListSerializer(serializers.ModelSerializer):
    plan_code = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "status",
            "is_email_verified",
            "locale",
            "plan_code",
            "roles",
            "created_at",
            "last_login_at",
        ]
        read_only_fields = fields

    def get_plan_code(self, user: User) -> str | None:
        subscription = getattr(user, "subscription", None)
        return subscription.plan.code if subscription else None

    def get_roles(self, user: User) -> list[str]:
        return list(user.user_roles.values_list("role__code", flat=True))


class AdminUserDetailSerializer(AdminUserListSerializer):
    class Meta(AdminUserListSerializer.Meta):
        fields = AdminUserListSerializer.Meta.fields + [
            "marketing_opt_in",
            "is_totp_enabled",
            "timezone",
        ]
        read_only_fields = fields


class SetRolesSerializer(serializers.Serializer):
    """POST /admin/users/{id}/roles body — replaces the full role set (FR-79)."""

    role_codes = serializers.ListField(
        child=serializers.CharField(max_length=32), allow_empty=True
    )

    def validate_role_codes(self, value: list[str]) -> list[str]:
        valid = set(Role.objects.filter(code__in=value).values_list("code", flat=True))
        missing = set(value) - valid
        if missing:
            raise serializers.ValidationError(
                f"Unknown role code(s): {sorted(missing)}"
            )
        return value


class AdminVideoJobSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = VideoJob
        fields = [
            "id",
            "user",
            "user_email",
            "channel",
            "status",
            "current_stage",
            "title",
            "error_code",
            "error_message",
            "retry_count",
            "total_cost_usd",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AdminPlanSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        request = self.context.get("request")
        if request and not (request.user.is_superuser and (request.user.is_totp_enabled or temporary_2fa_exemption(request.user))):
            raise serializers.ValidationError(
                "Only a superadmin with 2FA can edit commercial plans."
            )
        from decimal import Decimal

        for field in ("tax_pct", "discount_pct"):
            value = attrs.get(field, getattr(self.instance, field, 0))
            if not Decimal("0") <= value <= Decimal("100"):
                raise serializers.ValidationError(
                    {field: "Use a percentage between 0 and 100."}
                )
        if attrs.get("price_amount", 0) < 0:
            raise serializers.ValidationError(
                {"price_amount": "Price must not be negative."}
            )
        start = attrs.get(
            "discount_starts_at", getattr(self.instance, "discount_starts_at", None)
        )
        end = attrs.get(
            "discount_ends_at", getattr(self.instance, "discount_ends_at", None)
        )
        if start and end and end <= start:
            raise serializers.ValidationError("Discount end must be after its start.")
        return attrs

    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "name",
            "price_amount",
            "tax_pct",
            "discount_pct",
            "discount_label",
            "discount_starts_at",
            "discount_ends_at",
            "ai_budget_enabled",
            "stars_amount",
            "currency",
            "billing_interval",
            "videos_per_period",
            "max_video_duration_sec",
            "max_languages",
            "concurrent_jobs",
            "voice_cloning_enabled",
            "priority_queue",
            "sla_hours",
            "features",
            "is_active",
            "sort_order",
        ]
        read_only_fields = ["id", "code"]


class AdminProviderSerializer(serializers.ModelSerializer):
    """`secret_ref`'s resolved value is never exposed (C-5, FR-84) — only
    whether it currently resolves to something (`has_secret`).
    """

    has_secret = serializers.SerializerMethodField()

    class Meta:
        model = ApiCredentialConfig
        fields = [
            "id",
            "service",
            "provider",
            "display_name",
            "model_name",
            "is_primary",
            "is_active",
            "priority",
            "config",
            "unit_cost_usd",
            "cost_unit",
            "rate_limit_per_min",
            "has_secret",
        ]
        read_only_fields = ["id", "service", "provider"]

    def get_has_secret(self, obj: ApiCredentialConfig) -> bool:
        return obj.has_secret()


class RotateSecretSerializer(serializers.Serializer):
    """POST /admin/providers/{id}/rotate-secret body — a new `secret_ref`
    *name*, never a raw key (C-5).
    """

    secret_ref = serializers.CharField(max_length=128)
