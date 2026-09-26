from django.conf import settings
from rest_framework import serializers

from payoneer.models import PayoneerAccount, PayoneerPayee, PayoneerPayout

SECRETS = ("payment_token", "client_secret")


class AccountSerializer(serializers.ModelSerializer):
    # Secrets are write-only; an empty value on update keeps the stored one.
    payment_token = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=500
    )
    client_secret = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=500
    )
    payment_token_set = serializers.SerializerMethodField()
    client_secret_set = serializers.SerializerMethodField()
    # Declared explicitly so DRF does not attach unique validators from the
    # partial "one default" constraints; save_account moves the flag instead.
    is_default_checkout = serializers.BooleanField(required=False)
    is_default_payouts = serializers.BooleanField(required=False)
    checkout_ready = serializers.BooleanField(read_only=True)
    payouts_ready = serializers.BooleanField(read_only=True)
    notification_url = serializers.SerializerMethodField()

    class Meta:
        model = PayoneerAccount
        fields = [
            "id",
            "label",
            "environment",
            "is_active",
            "checkout_enabled",
            "is_default_checkout",
            "merchant_code",
            "division",
            "payment_token",
            "payment_token_set",
            "payouts_enabled",
            "is_default_payouts",
            "program_id",
            "client_id",
            "client_secret",
            "client_secret_set",
            "checkout_ready",
            "payouts_ready",
            "notification_url",
            "last_checked_at",
            "last_check_ok",
            "last_check_detail",
            "created_at",
        ]
        read_only_fields = ["last_checked_at", "last_check_ok", "last_check_detail"]

    def get_payment_token_set(self, obj):
        return bool(obj.payment_token_enc)

    def get_client_secret_set(self, obj):
        return bool(obj.client_secret_enc)

    def get_notification_url(self, obj):
        return f"{settings.BACKEND_BASE_URL.rstrip('/')}/api/v1/webhooks/payoneer/{obj.pk}/checkout"

    def validate(self, data):
        def value(field):
            if field in data:
                return data[field]
            if self.instance is not None:
                return getattr(self.instance, field)
            return PayoneerAccount._meta.get_field(field).default

        if value("is_default_checkout") and not value("checkout_enabled"):
            raise serializers.ValidationError(
                "The default checkout account must have checkout enabled."
            )
        if value("is_default_payouts") and not value("payouts_enabled"):
            raise serializers.ValidationError(
                "The default payout account must have payouts enabled."
            )
        if (value("is_default_checkout") or value("is_default_payouts")) and not value(
            "is_active"
        ):
            raise serializers.ValidationError("An inactive account cannot be the default.")
        return data

    def _apply_secrets(self, validated_data):
        for name in SECRETS:
            value = validated_data.pop(name, "")
            if value:
                validated_data[f"{name}_enc"] = value.strip()
        return validated_data

    def create(self, validated_data):
        return super().create(self._apply_secrets(validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._apply_secrets(validated_data))


class PayeeSerializer(serializers.ModelSerializer):
    account_label = serializers.CharField(source="account.label", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True, default="")
    user_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = PayoneerPayee
        fields = [
            "id",
            "account",
            "account_label",
            "user_id",
            "user_email",
            "display_name",
            "email",
            "payee_id",
            "status",
            "provider_status",
            "last_checked_at",
            "created_at",
        ]
        read_only_fields = ["payee_id", "status", "provider_status", "last_checked_at"]

    def validate_account(self, account):
        if not account.payouts_ready:
            raise serializers.ValidationError("This account is not set up for payouts.")
        return account

    def validate_user_id(self, value):
        from django.contrib.auth import get_user_model

        if value and not get_user_model().objects.filter(pk=value).exists():
            raise serializers.ValidationError("No such user.")
        return value


class PayoutSerializer(serializers.ModelSerializer):
    payee_name = serializers.CharField(source="payee.display_name", read_only=True)
    account_label = serializers.CharField(source="account.label", read_only=True)

    class Meta:
        model = PayoneerPayout
        fields = [
            "id",
            "account_label",
            "payee",
            "payee_name",
            "amount",
            "currency",
            "description",
            "client_reference_id",
            "status",
            "provider_status",
            "payout_id",
            "reason",
            "submitted_at",
            "last_checked_at",
            "created_at",
        ]
        read_only_fields = [
            "currency",
            "client_reference_id",
            "status",
            "provider_status",
            "payout_id",
            "reason",
            "submitted_at",
            "last_checked_at",
        ]
