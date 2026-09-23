"""Status and explicit verified activation for operator-provisioned private inference."""

import hashlib
import json
from datetime import timedelta

from audit.services import record_audit_event
from core.permissions import IsAdmin, IsStaffWith2FA
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from providers.exceptions import ProviderError
from providers.models import ApiCredentialConfig
from providers.services import record_api_usage
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from telegram_integration.views import IsSuperAdmin
from video_pipeline.services.ollama_client import OllamaClient


def row():
    return ApiCredentialConfig.objects.filter(
        provider="ollama", service="llm", deleted_at__isnull=True
    ).first()


def fingerprint(config):
    return hashlib.sha256(
        json.dumps(
            [
                config.model_name,
                settings.OLLAMA_BASE_URL,
                settings.OLLAMA_API_KEY,
                {k: v for k, v in config.config.items() if not k.startswith("test_")},
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def state(config):
    if not config:
        return {
            "configured": False,
            "active": False,
            "verified": False,
            "model": "qwen3:4b-instruct",
        }
    tested = parse_datetime(config.get_option("test_at", ""))
    verified = bool(
        tested
        and timezone.is_aware(tested)
        and tested > timezone.now() - timedelta(hours=1)
        and config.get_option("test_fingerprint") == fingerprint(config)
    )
    return {
        "configured": bool(settings.OLLAMA_BASE_URL),
        "active": config.is_active and config.is_primary,
        "verified": verified,
        "model": config.model_name,
        "tested_at": tested,
    }


class LocalTestThrottle(UserRateThrottle):
    scope = "local_llm_test"
    rate = "3/min"


class LocalLLMView(APIView):
    permission_classes = (IsAdmin, IsStaffWith2FA)

    def get_throttles(self):
        return [LocalTestThrottle()] if self.request.method == "POST" else []

    def get(self, request):
        return Response(
            {**state(row()), "can_manage": IsSuperAdmin().has_permission(request, self)}
        )

    def post(self, request):
        if not IsSuperAdmin().has_permission(request, self):
            raise PermissionDenied(
                "A superadmin with two-factor authentication is required."
            )
        config = row()
        if not config or not settings.OLLAMA_BASE_URL:
            raise ValidationError(
                "Provision a private Ollama endpoint and run seed_local_llm first."
            )
        action = request.data.get("action")
        if action == "test":
            version = config.updated_at
            try:
                result = OllamaClient(config).chat_completion(
                    messages=[
                        {
                            "role": "user",
                            "content": "Return a JSON object with ok set to true.",
                        }
                    ],
                    json_mode=True,
                    max_tokens=80,
                )
                if json.loads(result.content).get("ok") is not True:
                    raise ValueError()
            except (ProviderError, ValueError, AttributeError):
                with transaction.atomic():
                    current = ApiCredentialConfig.objects.select_for_update().get(
                        pk=config.pk
                    )
                    if current.updated_at == version:
                        current.config.pop("test_fingerprint", None)
                        current.save(update_fields=["config", "updated_at"])
                raise ValidationError(
                    "Local AI test failed. Check the private service, model, capacity and logs."
                ) from None
            if (
                record_api_usage(
                    config=config,
                    operation="admin_connection_test",
                    units=result.total_tokens,
                    unit_type="tokens",
                    cost_usd=0,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                )
                is None
            ):
                raise ValidationError("Could not record inference usage.")
            with transaction.atomic():
                current = ApiCredentialConfig.objects.select_for_update().get(
                    pk=config.pk
                )
                if current.updated_at != version:
                    raise ValidationError("Configuration changed; test again.")
                current.config["test_at"] = timezone.now().isoformat()
                current.config["test_fingerprint"] = fingerprint(current)
                current.save(update_fields=["config", "updated_at"])
                config = current
        elif action == "activate":
            with transaction.atomic():
                configs = list(
                    ApiCredentialConfig.objects.select_for_update()
                    .filter(service="llm", deleted_at__isnull=True)
                    .order_by("pk")
                )
                config = next(c for c in configs if c.pk == config.pk)
                if not state(config)["verified"]:
                    raise ValidationError(
                        "Run a successful test within the last hour before activation."
                    )
                ApiCredentialConfig.objects.filter(
                    service="llm", is_primary=True
                ).exclude(pk=config.pk).update(is_primary=False)
                config.is_active = config.is_primary = True
                config.save(update_fields=["is_active", "is_primary", "updated_at"])
        else:
            raise ValidationError("Unknown action.")
        record_audit_event(
            actor_type="staff",
            actor_id=request.user.pk,
            action="local_llm." + action,
            resource_type="api_credentials_config",
            resource_id=str(config.pk),
            request=request,
            metadata={"model": config.model_name},
        )
        return Response(state(config))
