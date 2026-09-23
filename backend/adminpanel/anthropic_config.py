"""Dedicated write-only key management, test and explicit primary-provider switch."""

from decimal import Decimal

from audit.services import record_audit_event
from core.permissions import IsAdmin, IsStaffWith2FA
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from providers.exceptions import ProviderError
from providers.models import ApiCredentialConfig, ProviderSecret
from providers.services import record_api_usage
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from telegram_integration.views import IsSuperAdmin
from video_pipeline.services.anthropic_client import AnthropicClient


class ConfigInput(serializers.Serializer):
    api_key = serializers.CharField(
        write_only=True, required=False, max_length=512, trim_whitespace=True
    )
    model = serializers.RegexField(r"^claude-[a-zA-Z0-9.-]+$", max_length=128)
    input_per_million = serializers.DecimalField(
        max_digits=10, decimal_places=4, min_value=Decimal(".0001"), max_value=1000
    )
    output_per_million = serializers.DecimalField(
        max_digits=10, decimal_places=4, min_value=Decimal(".0001"), max_value=1000
    )

    def validate_api_key(self, value):
        if not value.startswith("sk-ant-") or any(c.isspace() for c in value):
            raise serializers.ValidationError("Anthropic API key format is invalid.")
        return value


class TestThrottle(UserRateThrottle):
    scope = "anthropic_config_test"
    rate = "5/min"


def config_row():
    return (
        ApiCredentialConfig.objects.filter(
            provider="anthropic", service="llm", deleted_at__isnull=True
        )
        .order_by("created_at")
        .first()
    )


def state(config):
    if config is None:
        return {
            "configured": False,
            "active": False,
            "primary": False,
            "model": "claude-sonnet-4-5",
            "input_per_million": "3",
            "output_per_million": "15",
            "tested_at": None,
            "verified": False,
        }
    secret = ProviderSecret.objects.filter(provider_config=config).first()
    verified = bool(
        secret
        and secret.tested_at
        and secret.tested_config_version == config.updated_at
    )
    return {
        "configured": bool(secret),
        "active": config.is_active,
        "primary": config.is_primary,
        "model": config.model_name,
        "input_per_million": str(
            Decimal(str(config.get_option("input_cost_per_1k_usd", 0))) * 1000
        ),
        "output_per_million": str(
            Decimal(str(config.get_option("output_cost_per_1k_usd", 0))) * 1000
        ),
        "tested_at": secret.tested_at if secret else None,
        "verified": verified,
    }


def audit(request, action, config):
    record_audit_event(
        actor_type="staff",
        actor_id=request.user.pk,
        action=action,
        resource_type="api_credentials_config",
        resource_id=str(config.pk),
        request=request,
        metadata={"provider": "anthropic", "model": config.model_name},
    )


@method_decorator(sensitive_post_parameters("api_key"), name="dispatch")
class AnthropicConfigView(APIView):
    permission_classes = (IsAdmin, IsStaffWith2FA)

    def get_throttles(self):
        return (
            [TestThrottle()]
            if self.request.method == "POST"
            and self.request.data.get("action") == "test"
            else []
        )

    def get(self, request):
        return Response(
            {
                **state(config_row()),
                "can_manage": IsSuperAdmin().has_permission(request, self),
            }
        )

    def post(self, request):
        if not IsSuperAdmin().has_permission(request, self):
            raise PermissionDenied(
                "Only a superadmin with two-factor authentication can manage API keys."
            )
        action = request.data.get("action")
        if action == "save":
            data = ConfigInput(data=request.data)
            data.is_valid(raise_exception=True)
            values = data.validated_data
            # Never persist with an ephemeral DEBUG key that disappears on restart.
            if not settings.FIELD_ENCRYPTION_KEYS_RAW:
                raise ValidationError(
                    "Configure persistent field encryption on the server first."
                )
            with transaction.atomic():
                # A stable existing row serializes first-time creation too.
                from django.contrib.auth import get_user_model

                get_user_model().objects.select_for_update().order_by("pk").first()
                config = config_row()
                if not config:
                    if not values.get("api_key"):
                        raise ValidationError("Enter an Anthropic API key.")
                    config = ApiCredentialConfig.objects.create(
                        provider="anthropic",
                        service="llm",
                        is_active=False,
                        is_primary=False,
                    )
                config = ApiCredentialConfig.objects.select_for_update().get(
                    pk=config.pk
                )
                config.model_name = values["model"]
                config.display_name = "Claude · Anthropic Direct"
                config.is_active = False
                config.cost_unit = "per_1k_tokens"
                config.unit_cost_usd = values["output_per_million"] / 1000
                config.config = {
                    "input_cost_per_1k_usd": str(values["input_per_million"] / 1000),
                    "output_cost_per_1k_usd": str(values["output_per_million"] / 1000),
                    "request_timeout_sec": 90,
                    "max_output_tokens": 4000,
                    "json_mode": True,
                    "pricing_source": "https://platform.claude.com/docs/en/about-claude/pricing",
                }
                config.save()
                secret = ProviderSecret.objects.filter(provider_config=config).first()
                if not secret:
                    secret = ProviderSecret(provider_config=config)
                if values.get("api_key"):
                    secret.value_enc = values["api_key"]
                if not secret.value_enc:
                    raise ValidationError("Enter an Anthropic API key.")
                secret.tested_at = None
                secret.tested_config_version = None
                secret.save()
                audit(request, "anthropic.config.saved", config)
            return Response(state(config))
        config = config_row()
        if not config:
            raise ValidationError("Save the configuration first.")
        if action == "test":
            secret = ProviderSecret.objects.filter(provider_config=config).first()
            if not secret:
                raise ValidationError("Save the API key first.")
            secret_version = secret.updated_at
            config_version = config.updated_at
            try:
                client = AnthropicClient(config, api_key=secret.value_enc)
                client.check_model()
                result = client.chat_completion(
                    messages=[{"role": "user", "content": "Reply with OK."}],
                    max_tokens=16,
                    json_mode=False,
                )
            except ProviderError as exc:
                ProviderSecret.objects.filter(
                    provider_config=config, updated_at=secret_version
                ).update(tested_at=None, tested_config_version=None)
                audit(request, "anthropic.connection.failed", config)
                return Response(
                    {
                        "detail": "Anthropic ulanishi tekshirilmadi. Kalit, model, balans va API limitlarini tekshiring.",
                        "error_code": exc.error_code,
                    },
                    status=400,
                )
            log = record_api_usage(
                config=config,
                operation="admin_connection_test",
                user=None,
                units=result.total_tokens,
                unit_type="tokens",
                cost_usd=result.provider_cost_usd,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                request_id=result.request_id,
            )
            if log is None:
                raise ValidationError(
                    "Could not record the test cost; activation is blocked."
                )
            with transaction.atomic():
                config = ApiCredentialConfig.objects.select_for_update().get(
                    pk=config.pk
                )
                current = ProviderSecret.objects.select_for_update().get(
                    provider_config=config
                )
                if (
                    current.updated_at != secret_version
                    or config.updated_at != config_version
                ):
                    raise ValidationError(
                        "Configuration changed during testing. Test the saved configuration again."
                    )
                current.tested_at = timezone.now()
                current.tested_config_version = config.updated_at
                current.save(update_fields=["tested_at", "tested_config_version"])
                audit(request, "anthropic.connection.verified", config)
            return Response(
                {**state(config), "test_cost_usd": str(result.provider_cost_usd)}
            )
        if action == "activate":
            with transaction.atomic():
                # Consistent lock order across all primary-provider switches.
                rows = list(
                    ApiCredentialConfig.objects.select_for_update()
                    .filter(service="llm", deleted_at__isnull=True)
                    .order_by("pk")
                )
                config = next(c for c in rows if c.pk == config.pk)
                if not state(config)["verified"]:
                    raise ValidationError(
                        "Run a successful test after the last configuration change."
                    )
                ApiCredentialConfig.objects.filter(
                    service="llm", is_primary=True
                ).exclude(pk=config.pk).update(is_primary=False)
                config.is_primary = True
                config.is_active = True
                config.save(update_fields=["is_primary", "is_active", "updated_at"])
                ProviderSecret.objects.filter(provider_config=config).update(
                    tested_config_version=config.updated_at
                )
                audit(request, "anthropic.primary.activated", config)
            return Response(state(config))
        raise ValidationError("Unknown action.")
