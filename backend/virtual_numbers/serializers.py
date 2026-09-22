from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from virtual_numbers.models import NumberOffer, NumberOrder, PhoneNumber
from virtual_numbers.pricing import quote
from virtual_numbers.services import unavailable_reason


class OfferSerializer(serializers.ModelSerializer):
    unavailable_reason = serializers.SerializerMethodField()
    available_count = serializers.SerializerMethodField()
    price_breakdown = serializers.SerializerMethodField()
    price_usd = serializers.SerializerMethodField()

    class Meta:
        model = NumberOffer
        fields = [
            "id",
            "name",
            "country_code",
            "country_name",
            "service",
            "number_type",
            "provider",
            "price_usd",
            "price_breakdown",
            "rental_days",
            "description",
            "unavailable_reason",
            "available_count",
        ]

    def get_price_breakdown(self, obj):
        return (
            quote(obj.base_cost_usd, obj.tax_basis)
            if obj.base_cost_usd is not None
            else None
        )

    def get_price_usd(self, obj):
        return (
            self.get_price_breakdown(obj)["total"]
            if obj.base_cost_usd is not None
            else str(obj.price_usd)
        )

    def get_unavailable_reason(self, obj):
        return unavailable_reason(obj)

    def get_available_count(self, obj):
        return obj.numbers.filter(state="available").count()


class AdminOfferSerializer(OfferSerializer):
    base_cost_usd = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=1, required=True
    )

    class Meta(OfferSerializer.Meta):
        fields = OfferSerializer.Meta.fields + [
            "base_cost_usd",
            "tax_basis",
            "is_visible",
            "sales_enabled",
            "contract_confirmed",
            "compatibility_confirmed",
        ]

    def validate(self, attrs):
        if not self.instance and "base_cost_usd" not in attrs:
            raise serializers.ValidationError("Provider base cost is required.")
        current = {
            f: getattr(self.instance, f, None)
            for f in [
                "service",
                "number_type",
                "sales_enabled",
                "contract_confirmed",
                "compatibility_confirmed",
            ]
        }
        current.update(attrs)
        if current.get("sales_enabled"):
            if not current.get("contract_confirmed") or not current.get(
                "compatibility_confirmed"
            ):
                raise serializers.ValidationError(
                    "Confirm the contract and service compatibility before enabling sales."
                )
            if (
                current.get("service") in ("telegram", "whatsapp")
                and current.get("number_type") != "mobile"
            ):
                raise serializers.ValidationError(
                    "Telegram and WhatsApp offers require mobile numbers."
                )
        if self.instance and self.instance.numbers.exists():
            for field in ("provider", "country_code", "service", "number_type"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError(
                        "Create a new offer to change the provider, country, service or number type after adding inventory."
                    )
        return attrs


class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PhoneNumber
        fields = ["id", "offer", "number", "provider_reference", "state"]
        read_only_fields = ["state"]


class OrderSerializer(serializers.ModelSerializer):
    number = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    checkout_url = serializers.SerializerMethodField()

    class Meta:
        model = NumberOrder
        fields = [
            "id",
            "offer_name",
            "service",
            "price_usd",
            "price_breakdown",
            "payment_provider",
            "rental_days",
            "status",
            "number",
            "checkout_url",
            "activated_at",
            "expires_at",
            "created_at",
            "refund_reason",
        ]

    def get_number(self, obj):
        return (
            obj.phone.number if obj.activated_at and obj.status != "refunded" else None
        )

    def get_status(self, obj):
        if (
            obj.status == "active"
            and obj.expires_at
            and obj.expires_at <= timezone.now()
        ):
            return "expired"
        return obj.status

    def get_checkout_url(self, obj):
        return (
            obj.checkout_url
            if obj.status == "pending"
            and (
                obj.payment_provider != "stripe"
                or obj.created_at > timezone.now() - timedelta(hours=1)
            )
            else ""
        )


class PurchaseSerializer(serializers.Serializer):
    offer_id = serializers.UUIDField()
    request_key = serializers.UUIDField()
    terms_accepted = serializers.BooleanField()
    payment_provider = serializers.ChoiceField(
        choices=["stripe", "paypal", "allpay"], default="stripe"
    )
    quoted_total = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=1
    )

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError("Please accept the rental terms.")
        return value


class SMSSerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=160)
    provider_reference = serializers.CharField(max_length=160)
    to = serializers.RegexField(r"^\+[1-9][0-9]{6,14}$", max_length=16)
    sender = serializers.CharField(max_length=160)
    body = serializers.CharField(max_length=4096)
    received_at = serializers.DateTimeField()


class RefundSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, min_length=5)
