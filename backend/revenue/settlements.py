from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from core.permissions import IsFinanceOrAdmin, IsStaffWith2FA
from revenue.models import RevenueSettlement, RevenueShareStatement
from video_pipeline.models import VideoJob
from audit.services import record_audit_event


class SettlementInput(serializers.Serializer):
    job_id = serializers.UUIDField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    evidence_reference = serializers.CharField(max_length=500, min_length=10)

    def validate(self, data):
        # Monthly half-open periods align exactly with service-fee statements.
        start, end = data["period_start"], data["period_end"]
        if (
            start.day != 1
            or end.day != 1
            or (end.year * 12 + end.month) - (start.year * 12 + start.month) != 1
        ):
            raise serializers.ValidationError(
                "Supply one complete calendar month, with an exclusive end date."
            )
        from django.utils import timezone

        if end > timezone.now().date():
            raise serializers.ValidationError(
                "A future revenue period cannot be settled."
            )
        return data


class SettlementView(APIView):
    permission_classes = [IsFinanceOrAdmin, IsStaffWith2FA]

    def get(self, request):
        return Response(
            list(
                RevenueSettlement.objects.order_by("-verified_at").values(
                    "id",
                    "job_id",
                    "user_id",
                    "period_start",
                    "period_end",
                    "amount",
                    "currency",
                    "evidence_reference",
                    "verified_at",
                )[:100]
            )
        )

    @transaction.atomic
    def post(self, request):
        data = SettlementInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        job = get_object_or_404(
            VideoJob.objects.select_for_update(),
            pk=values.pop("job_id"),
            is_platform_generated=True,
            youtube_upload_status="uploaded",
            published_at__isnull=False,
        )
        if not job.youtube_video_id:
            raise serializers.ValidationError("An ecosystem upload record is required.")
        from accounts.models import User

        User.objects.select_for_update().get(pk=job.user_id)
        existing = RevenueSettlement.objects.filter(
            job=job,
            period_start=values["period_start"],
            period_end=values["period_end"],
        ).first()
        if existing:
            if (
                existing.amount != values["amount"]
                or existing.evidence_reference != values["evidence_reference"]
            ):
                raise serializers.ValidationError(
                    "A verified settlement is immutable; use a separately audited correction."
                )
            return Response({"id": str(existing.pk)}, status=200)
        if RevenueShareStatement.objects.filter(
            user=job.user,
            period_start=values["period_start"],
            period_end=values["period_end"],
        ).exists():
            raise serializers.ValidationError(
                "A statement already exists for this period; reconcile it before adding revenue."
            )
        settlement = RevenueSettlement.objects.create(
            user=job.user, job=job, verified_by=request.user, **values
        )
        record_audit_event(
            actor_type="staff",
            actor_id=request.user.pk,
            action="revenue.settlement_verified",
            resource_type="revenue_settlement",
            resource_id=str(settlement.pk),
            after={
                "job_id": str(job.pk),
                "amount": str(settlement.amount),
                "evidence_reference": settlement.evidence_reference,
            },
        )
        return Response({"id": str(settlement.pk)}, status=201)
