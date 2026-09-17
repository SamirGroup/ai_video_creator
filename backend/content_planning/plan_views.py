from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from content_planning.models import ContentPlan, ContentPlanItem
from content_planning.proposals import create_proposal, approve_proposal
from content_planning.services import get_owned_channel


class PlanItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentPlanItem
        fields = [
            "id",
            "position",
            "title",
            "brief",
            "rationale",
            "scheduled_for",
            "selected",
            "job",
        ]
        read_only_fields = ["id", "position", "job"]

    def validate_scheduled_for(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Publication time must be in the future.")
        return value


class PlanSerializer(serializers.ModelSerializer):
    items = PlanItemSerializer(many=True, read_only=True)

    class Meta:
        model = ContentPlan
        fields = [
            "id",
            "channel",
            "horizon",
            "status",
            "summary",
            "analysis",
            "preference_snapshot",
            "cost_usd",
            "error_code",
            "created_at",
            "approved_at",
            "items",
        ]
        read_only_fields = fields


class ProposalInput(serializers.Serializer):
    request_key = serializers.UUIDField()
    horizon = serializers.ChoiceField(choices=["daily", "weekly", "monthly"])
    count = serializers.IntegerField(min_value=1, max_value=30, default=1)

    def validate(self, data):
        if data["count"] > {"daily": 1, "weekly": 7, "monthly": 30}[data["horizon"]]:
            raise serializers.ValidationError("At most one planned video per day.")
        return data


class ChannelPlansView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, channel_id):
        channel = get_owned_channel(request.user, channel_id)
        return Response(
            PlanSerializer(
                ContentPlan.objects.filter(channel=channel)
                .prefetch_related("items")
                .order_by("-created_at")[:50],
                many=True,
            ).data
        )

    def post(self, request, channel_id):
        channel = get_owned_channel(request.user, channel_id)
        data = ProposalInput(data=request.data)
        data.is_valid(raise_exception=True)
        plan = create_proposal(request.user, channel, **data.validated_data)
        return Response(PlanSerializer(plan).data, status=status.HTTP_202_ACCEPTED)


class PlanDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, plan_id):
        plan = get_object_or_404(
            ContentPlan.objects.prefetch_related("items"), pk=plan_id, user=request.user
        )
        return Response(PlanSerializer(plan).data)


class PlanItemView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, plan_id, item_id):
        plan = get_object_or_404(
            ContentPlan.objects.select_for_update(), pk=plan_id, user=request.user
        )
        if plan.status != "ready":
            raise serializers.ValidationError(
                "Only an unapproved ready plan can be edited."
            )
        item = get_object_or_404(ContentPlanItem, pk=item_id, plan=plan)
        serializer = PlanItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ApprovePlanView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, plan_id):
        get_object_or_404(ContentPlan, pk=plan_id, user=request.user)
        serializer = serializers.ListField(
            child=serializers.UUIDField(), allow_empty=False, max_length=30
        )
        item_ids = serializer.run_validation(request.data.get("item_ids"))
        plan = approve_proposal(request.user, plan_id, item_ids)
        return Response(PlanSerializer(plan).data)
