from __future__ import annotations

from rest_framework import serializers

from contracts.models import Contract, ContractVersion


class ContractVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractVersion
        fields = [
            "id",
            "version",
            "title",
            "body_markdown",
            "body_sha256",
            "locale",
            "revenue_share_platform_pct",
            "revenue_share_creator_pct",
            "effective_from",
        ]
        read_only_fields = fields


class ContractSerializer(serializers.ModelSerializer):
    version = serializers.CharField(source="contract_version.version", read_only=True)
    title = serializers.CharField(source="contract_version.title", read_only=True)
    has_pdf = serializers.SerializerMethodField()

    class Meta:
        model = Contract
        fields = [
            "id",
            "contract_version",
            "version",
            "title",
            "signed_at",
            "body_sha256",
            "consent_revenue_share",
            "consent_publish_to_channel",
            "consent_data_processing",
            "consent_marketing",
            "status",
            "terminated_at",
            "has_pdf",
        ]
        read_only_fields = fields

    def get_has_pdf(self, obj) -> bool:
        return bool(obj.pdf_s3_key)


class SignContractSerializer(serializers.Serializer):
    """FR-30: granular consents. (a)(b)(c) must be explicitly true; (d) optional, default off."""

    contract_version_id = serializers.UUIDField(required=False)
    consent_revenue_share = serializers.BooleanField()
    consent_publish_to_channel = serializers.BooleanField()
    consent_data_processing = serializers.BooleanField()
    consent_marketing = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        errors = {
            name: "This consent is required to use the service."
            for name in ("consent_revenue_share", "consent_publish_to_channel", "consent_data_processing")
            if not attrs.get(name)
        }
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class CurrentContractSerializer(serializers.Serializer):
    version = ContractVersionSerializer(allow_null=True)
    signed = serializers.BooleanField()
    signed_contract = ContractSerializer(allow_null=True)
    has_payment_method = serializers.BooleanField()
    requires_signature = serializers.BooleanField()
    requires_resign = serializers.BooleanField()
    generation_allowed = serializers.BooleanField()
    generation_block_code = serializers.CharField(allow_null=True)
