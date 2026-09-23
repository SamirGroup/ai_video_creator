from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from audit.services import record_audit_event
from core.permissions import HasRole, IsAdmin, IsStaffWith2FA
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from providers.exceptions import ProviderNotConfigured
from providers.services import get_primary_config, ensure_provider_ready
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from content_planning.assistant import creator_context, overview, respond
from content_planning.assistant_models import (
    AssistantPolicy,
    AssistantProfile,
    AssistantTurn,
)


class IsCreator(HasRole):
    allowed_roles = {"creator"}


class ProfileSerializer(serializers.ModelSerializer):
    from core.languages import LANGUAGE_CODES

    language = serializers.ChoiceField(choices=LANGUAGE_CODES)

    class Meta:
        model = AssistantProfile
        fields = [
            "goal",
            "audience_region",
            "language",
            "timezone",
            "onboarding_completed",
        ]

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Choose a valid IANA timezone.")
        return value


class TurnSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantTurn
        fields = [
            "id",
            "question",
            "answer",
            "status",
            "error_code",
            "cost_usd",
            "created_at",
        ]
        read_only_fields = fields


class MessageInput(serializers.Serializer):
    message = serializers.CharField(max_length=3000)
    request_key = serializers.UUIDField()


class PolicySerializer(serializers.ModelSerializer):
    daily_message_limit = serializers.IntegerField(min_value=1, max_value=100)

    class Meta:
        model = AssistantPolicy
        fields = ["enabled", "daily_message_limit", "guidance"]


class AssistantView(APIView):
    permission_classes = [IsAuthenticated, IsCreator]

    def get(self, request):
        policy, _ = AssistantPolicy.objects.get_or_create(pk=1)
        context = creator_context(request.user)
        try:
            ensure_provider_ready(get_primary_config("llm"))
            ready = True
        except ProviderNotConfigured:
            ready = False
        # Hard task timeout is 180 seconds; expired jobs must not block a user forever.
        from billing.wallet import release_operation

        for turn in AssistantTurn.objects.filter(
            user=request.user,
            status__in=["pending", "running"],
            created_at__lt=timezone.now() - timedelta(minutes=10),
        ):
            if AssistantTurn.objects.filter(
                pk=turn.pk, status__in=["pending", "running"]
            ).update(status="failed", error_code="WORKER_TIMEOUT"):
                release_operation(f"assistant:{turn.pk}")
        return Response(
            {
                **context,
                "available": policy.enabled and ready,
                "daily_message_limit": policy.daily_message_limit,
                "turns": TurnSerializer(
                    AssistantTurn.objects.filter(user=request.user).order_by(
                        "-created_at"
                    )[:30],
                    many=True,
                ).data,
            }
        )

    def patch(self, request):
        profile, _ = AssistantProfile.objects.get_or_create(user=request.user)
        data = ProfileSerializer(profile, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        return Response(data.data)

    def post(self, request):
        data = MessageInput(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            previous = AssistantTurn.objects.filter(
                user=request.user, request_key=data.validated_data["request_key"]
            ).first()
            if previous:
                if previous.question != data.validated_data["message"]:
                    raise ValidationError("Request key belongs to another message.")
                return Response(TurnSerializer(previous).data)
            policy, _ = AssistantPolicy.objects.get_or_create(pk=1)

            try:
                if not policy.enabled:
                    raise ValueError()
                ensure_provider_ready(get_primary_config("llm"))
            except (ProviderNotConfigured, ValueError):
                return Response(
                    {
                        "detail": "AI yordamchi hali ulanmagan yoki admin tomonidan to‘xtatilgan."
                    },
                    status=503,
                )
            if (
                AssistantTurn.objects.filter(
                    user=request.user,
                    created_at__gte=timezone.now() - timedelta(days=1),
                ).count()
                >= policy.daily_message_limit
            ):
                raise ValidationError("Kunlik AI suhbat limiti tugadi.")
            if AssistantTurn.objects.filter(
                user=request.user, status__in=["pending", "running"]
            ).exists():
                raise ValidationError("Oldingi so‘rov yakunlanishini kuting.")
            turn = AssistantTurn.objects.create(
                user=request.user,
                question=data.validated_data["message"],
                request_key=data.validated_data["request_key"],
            )
        try:
            respond.apply_async(args=[str(turn.pk)], queue="q_script")
        except Exception:
            turn.status = "failed"
            turn.error_code = "QUEUE_UNAVAILABLE"
            turn.save(update_fields=["status", "error_code"])
        return Response(TurnSerializer(turn).data, status=202)


class AssistantAdminView(APIView):
    permission_classes = [IsAdmin, IsStaffWith2FA]

    def get(self, request):
        policy, _ = AssistantPolicy.objects.get_or_create(pk=1)
        return Response({**overview(), "policy": PolicySerializer(policy).data})

    def patch(self, request):
        policy, _ = AssistantPolicy.objects.get_or_create(pk=1)
        data = PolicySerializer(policy, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        record_audit_event(
            actor_type="user",
            actor_id=request.user.pk,
            action="assistant.policy.updated",
            resource_type="AssistantPolicy",
            resource_id="1",
            metadata={
                "enabled": policy.enabled,
                "daily_message_limit": policy.daily_message_limit,
            },
        )
        return Response(data.data)
