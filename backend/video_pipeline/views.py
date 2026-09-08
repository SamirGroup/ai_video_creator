from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from channels.models import YouTubeChannel
from video_pipeline.models import VideoJob, VideoJobStep
from video_pipeline.serializers import (
    RejectVideoSerializer,
    RequestChangesSerializer,
    VideoJobDetailSerializer,
    VideoJobListSerializer,
    VideoJobStepSerializer,
    VideoMetadataUpdateSerializer,
)
from video_pipeline.services import approval


class VideoJobListView(ListAPIView):
    """GET /api/v1/videos (filter: status, date)."""

    serializer_class = VideoJobListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status"]

    def get_queryset(self):
        return VideoJob.objects.filter(user=self.request.user).order_by("-created_at")


class VideoJobDetailView(RetrieveAPIView):
    """GET /api/v1/videos/{id} — owner-scoped (no IDOR)."""

    serializer_class = VideoJobDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "job_id"

    def get_queryset(self):
        return VideoJob.objects.filter(user=self.request.user)


class VideoJobStepsView(ListAPIView):
    """GET /api/v1/videos/{id}/steps."""

    serializer_class = VideoJobStepSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return VideoJobStep.objects.filter(
            job_id=self.kwargs["job_id"], job__user=self.request.user
        ).order_by("-started_at")


def _get_owned_job(user, job_id) -> VideoJob | None:
    """Owner-scoped lookup shared by every job-mutating endpoint below — 404
    (not 403) on a foreign job so existence is never leaked (no IDOR).
    """
    return VideoJob.objects.select_related("preference", "channel", "user").filter(id=job_id, user=user).first()


def _job_not_found() -> Response:
    return Response({"detail": "Video job not found."}, status=status.HTTP_404_NOT_FOUND)


class GenerateVideoView(APIView):
    """POST /api/v1/videos/generate (FR-36 manual trigger; gates + quota, AC-3).

    Body: {"channel_id": uuid}  (optional when the creator has exactly one channel).
    202 with the queued job; 402 QUOTA_EXCEEDED / 409 CONCURRENT_JOBS_LIMIT /
    403 CONTRACT_NOT_SIGNED|PAYMENT_METHOD_REQUIRED|SUBSCRIPTION_INACTIVE.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from content_planning import services as planning
        from content_planning.serializers import GenerateVideoSerializer

        serializer = GenerateVideoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channel_id = serializer.validated_data.get("channel_id")
        if channel_id is None:
            channels = list(YouTubeChannel.objects.filter(user=request.user, deleted_at__isnull=True)[:2])
            if len(channels) != 1:
                return Response({"detail": "channel_id is required."}, status=status.HTTP_400_BAD_REQUEST)
            channel = channels[0]
        else:
            channel = planning.get_owned_channel(request.user, channel_id)
        job = planning.generate_now(request.user, channel, request=request)
        return Response(VideoJobDetailSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class CancelVideoJobView(APIView):
    """POST /api/v1/videos/{id}/cancel (FR-36). Owner-scoped; quota refunded if generation had not started."""

    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        from content_planning import services as planning

        job = VideoJob.objects.filter(id=job_id, user=request.user).first()
        if job is None:
            return Response({"detail": "Video job not found."}, status=status.HTTP_404_NOT_FOUND)
        job = planning.cancel_job(request.user, job, request=request)
        return Response(VideoJobDetailSerializer(job).data)


class UpdateVideoMetadataView(APIView):
    """PATCH /api/v1/videos/{id}/metadata (FR-41) — editable up to the approval decision."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, job_id):
        job = _get_owned_job(request.user, job_id)
        if job is None:
            return _job_not_found()
        serializer = VideoMetadataUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = approval.update_metadata(request.user, job, serializer.validated_data, request=request)
        return Response(VideoJobDetailSerializer(job).data)


class VideoPreviewView(APIView):
    """GET /api/v1/videos/{id}/preview — signed preview URL (NFR-7)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        job = _get_owned_job(request.user, job_id)
        if job is None:
            return _job_not_found()
        if not job.final_video_s3_key:
            return Response(
                {"detail": "No preview is available for this video yet."}, status=status.HTTP_409_CONFLICT
            )
        job = approval.ensure_preview_token(job)
        return Response({"preview_url": approval.preview_url(job), "expires_at": job.preview_expires_at})


class ApproveVideoView(APIView):
    """POST /api/v1/videos/{id}/approve (FR-39)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        job = _get_owned_job(request.user, job_id)
        if job is None:
            return _job_not_found()
        job = approval.approve_job(request.user, job, request=request)
        return Response(VideoJobDetailSerializer(job).data)


class RequestChangesVideoView(APIView):
    """POST /api/v1/videos/{id}/request-changes (FR-39, A-21)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        job = _get_owned_job(request.user, job_id)
        if job is None:
            return _job_not_found()
        serializer = RequestChangesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = approval.request_changes(
            request.user,
            job,
            comment=serializer.validated_data["comment"],
            restart_stage=serializer.validated_data["restart_stage"],
            request=request,
        )
        return Response(VideoJobDetailSerializer(job).data)


class RejectVideoView(APIView):
    """POST /api/v1/videos/{id}/reject (FR-39) — terminal, no quota refund."""

    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        job = _get_owned_job(request.user, job_id)
        if job is None:
            return _job_not_found()
        serializer = RejectVideoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = approval.reject_job(request.user, job, serializer.validated_data["reason"], request=request)
        return Response(VideoJobDetailSerializer(job).data)
