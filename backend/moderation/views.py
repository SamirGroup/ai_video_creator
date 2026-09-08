from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import UpdatedAtCursorPagination
from core.permissions import IsModeratorOrAdmin
from moderation import services
from moderation.serializers import ModerationDecisionSerializer, ModerationQueueItemSerializer
from video_pipeline.models import VideoJob


class ModerationQueueView(ListAPIView):
    """GET /api/v1/admin/moderation/queue (FR-48, FR-81)."""

    serializer_class = ModerationQueueItemSerializer
    permission_classes = [IsModeratorOrAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = []
    pagination_class = UpdatedAtCursorPagination

    def get_queryset(self):
        return services.moderation_queue(stage=self.request.query_params.get("stage"))


class ModerationDecideView(APIView):
    """POST /api/v1/admin/moderation/{job_id}/decide (FR-48, FR-81)."""

    permission_classes = [IsModeratorOrAdmin]

    def post(self, request, job_id):
        job = VideoJob.objects.filter(id=job_id).select_related("user", "preference").first()
        if job is None:
            return Response({"detail": "Video job not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ModerationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = services.decide(
            request.user,
            job,
            decision=serializer.validated_data["decision"],
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response({"id": str(job.pk), "status": job.status})
