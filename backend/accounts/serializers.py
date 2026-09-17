from __future__ import annotations

from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "is_email_verified",
            "locale",
            "timezone",
            "status",
            "is_totp_enabled",
            "marketing_opt_in",
            "roles",
            "created_at",
        ]
        read_only_fields = fields

    def get_roles(self, obj: User) -> list[str]:
        return list(obj.user_roles.values_list("role__code", flat=True))


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["full_name", "locale", "timezone", "marketing_opt_in"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    marketing_opt_in = serializers.BooleanField(required=False, default=False)

    def validate_email(self, value: str) -> str:
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalized

    def validate_password(self, value: str) -> str:
        # FR-1: minimum 10 characters + Django's common/numeric/similarity validators.
        if len(value) < 10:
            raise serializers.ValidationError("Password must be at least 10 characters long.")
        try:
            password_validation.validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data.get("full_name", ""),
            marketing_opt_in=validated_data.get("marketing_opt_in", False),
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs: dict) -> dict:
        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs["email"].strip().lower(),
            password=attrs["password"],
        )
        if user is None:
            # authenticate() also returns None for inactive users (is_active
            # property is derived from `status`), so this covers both wrong
            # credentials and suspended/deleted accounts without leaking which.
            raise serializers.ValidationError("Invalid email or password.", code="authentication_failed")
        attrs["user"] = user
        return attrs


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value: str) -> str:
        if len(value) < 10:
            raise serializers.ValidationError("Password must be at least 10 characters long.")
        try:
            password_validation.validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField()
