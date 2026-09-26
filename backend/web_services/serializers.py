from datetime import date

from rest_framework import serializers

from web_services.contract import PACKAGES
from web_services.models import ContractType, ExecutorProfile, ServiceOrder, ServicePackage


class PackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePackage
        fields = [
            "id",
            "code",
            "price_usd",
            "delivery_days",
            "revision_rounds",
            "support_months",
            "page_limit",
            "languages",
        ]


class AdminPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePackage
        fields = PackageSerializer.Meta.fields + ["sort_order", "is_active"]
        read_only_fields = ["code"]


class ExecutorSerializer(serializers.ModelSerializer):
    complete = serializers.BooleanField(read_only=True)

    class Meta:
        model = ExecutorProfile
        exclude = ["id"]
        read_only_fields = ["updated_at"]


def _adult(value):
    today = date.today()
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if age < 18:
        raise serializers.ValidationError("The customer must be at least 18 years old.")
    return value


class CustomerSerializer(serializers.Serializer):
    full_name = serializers.CharField(min_length=5, max_length=160)
    date_of_birth = serializers.DateField(validators=[_adult])
    passport_number = serializers.RegexField(r"^[A-Z0-9]{5,20}$", max_length=20)
    passport_issued_by = serializers.CharField(min_length=2, max_length=160)
    passport_issued_at = serializers.DateField()
    address = serializers.CharField(min_length=5, max_length=240)
    city = serializers.CharField(min_length=2, max_length=80)
    phone = serializers.RegexField(r"^\+[1-9][0-9 ()-]{6,20}$", max_length=24)
    email = serializers.EmailField()
    # Resident only.
    pinfl = serializers.RegexField(r"^[0-9]{14}$", required=False, allow_blank=True)
    # Non-resident only.
    citizenship = serializers.CharField(max_length=80, required=False, allow_blank=True)
    citizenship_code = serializers.RegexField(r"^[A-Z]{2}$", required=False, allow_blank=True)
    country = serializers.CharField(max_length=80, required=False, allow_blank=True)
    country_code = serializers.RegexField(r"^[A-Z]{2}$", required=False, allow_blank=True)
    tax_id = serializers.CharField(max_length=40, required=False, allow_blank=True)

    def validate_passport_issued_at(self, value):
        if value > date.today():
            raise serializers.ValidationError("The issue date cannot be in the future.")
        return value

    def validate_for(self, kind):
        data = dict(self.validated_data)
        if kind == ContractType.RESIDENT:
            if not data.get("pinfl"):
                raise serializers.ValidationError({"pinfl": "PINFL is required for residents."})
            data.update(citizenship="O‘zbekiston", citizenship_code="UZ", country="O‘zbekiston",
                        country_code="UZ", tax_id="")
        else:
            missing = [f for f in ("citizenship", "citizenship_code", "country", "country_code") if not data.get(f)]
            if missing:
                raise serializers.ValidationError({f: "This field is required." for f in missing})
            if data["citizenship_code"] == "UZ":
                raise serializers.ValidationError(
                    {"citizenship_code": "Citizens of Uzbekistan sign the resident contract."}
                )
            data["pinfl"] = ""
        for key in ("date_of_birth", "passport_issued_at"):
            data[key] = data[key].isoformat()
        data["full_name"] = " ".join(data["full_name"].split())
        return data


class ProjectSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=3, max_length=160)
    description = serializers.CharField(min_length=20, max_length=4000)
    reference_url = serializers.URLField(required=False, allow_blank=True, max_length=300)


class DraftSerializer(serializers.Serializer):
    package = serializers.SlugRelatedField(
        slug_field="code", queryset=ServicePackage.objects.filter(is_active=True)
    )
    contract_type = serializers.ChoiceField(choices=ContractType.choices)
    customer = serializers.DictField()
    project = ProjectSerializer()

    def validate_package(self, package):
        if package.code not in PACKAGES:
            raise serializers.ValidationError("This package has no contract wording.")
        return package

    def validate(self, data):
        customer = CustomerSerializer(data=data["customer"])
        customer.is_valid(raise_exception=True)
        data["customer"] = customer.validate_for(data["contract_type"])
        return data


class OrderInputSerializer(DraftSerializer):
    request_key = serializers.UUIDField()
    quoted_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    # Checksum of the preview the customer read; any drift means re-reading.
    preview_checksum = serializers.RegexField(r"^[0-9a-f]{64}$")
    accept_terms = serializers.BooleanField()

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError("The contract terms must be accepted.")
        return value


class OrderSerializer(serializers.ModelSerializer):
    package = serializers.CharField(source="package.code")

    class Meta:
        model = ServiceOrder
        fields = [
            "id",
            "number",
            "package",
            "price_usd",
            "currency",
            "contract_type",
            "project_name",
            "status",
            "checkout_url",
            "paid_at",
            "accepted_at",
            "created_at",
        ]


class AdminOrderSerializer(OrderSerializer):
    user_email = serializers.EmailField(source="user.email")
    account_label = serializers.CharField(source="account.label", default="")

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + [
            "user_email",
            "account_label",
            "charge_id",
            "admin_note",
            "contract_sha256",
        ]
