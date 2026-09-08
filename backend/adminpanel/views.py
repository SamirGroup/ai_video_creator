from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from adminpanel import services
from adminpanel.serializers import (
    AdminPlanSerializer,
    AdminProviderSerializer,
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AdminVideoJobSerializer,
    RotateSecretSerializer,
    SetRolesSerializer,
)
from billing.models import Plan
from core.pagination import (
    CreatedAtCursorPagination,
    ServicePriorityCursorPagination,
    SortOrderCursorPagination,
    UpdatedAtCursorPagination,
)
from core.permissions import IsAdmin, IsSupportOrAdmin
from providers.models import ApiCredentialConfig
from video_pipeline.models import VideoJob


# ---------------------------------------------------------------------------
# Users (FR-79)
# ---------------------------------------------------------------------------
class AdminUserListView(ListAPIView):
    """GET /api/v1/admin/users?status=&search=."""

    serializer_class = AdminUserListSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status"]
    pagination_class = CreatedAtCursorPagination

    def get_queryset(self):
        qs = User.objects.all().select_related("subscription__plan").order_by("-created_at")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(email__icontains=search)
        return qs


class AdminUserDetailView(APIView):
    """GET /api/v1/admin/users/{id} (FR-88: viewing is itself audited)."""

    permission_classes = [IsAdmin]

    def get(self, request, user_id):
        user = User.objects.filter(id=user_id).select_related("subscription__plan").first()
        if user is None:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        services.view_user(request.user, user, request=request)
        return Response(AdminUserDetailSerializer(user).data)


class AdminUserSuspendView(APIView):
    """POST /api/v1/admin/users/{id}/suspend."""

    permission_classes = [IsAdmin]

    def post(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if user is None:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        user = services.suspend_user(request.user, user, request=request)
        return Response(AdminUserDetailSerializer(user).data)


class AdminUserReactivateView(APIView):
    """POST /api/v1/admin/users/{id}/reactivate."""

    permission_classes = [IsAdmin]

    def post(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if user is None:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        user = services.reactivate_user(request.user, user, request=request)
        return Response(AdminUserDetailSerializer(user).data)


class AdminUserRolesView(APIView):
    """POST /api/v1/admin/users/{id}/roles — replaces the full role set."""

    permission_classes = [IsAdmin]

    def post(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if user is None:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SetRolesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.set_roles(request.user, user, serializer.validated_data["role_codes"], request=request)
        return Response(AdminUserDetailSerializer(user).data)


# ---------------------------------------------------------------------------
# Video jobs (FR-80)
# ---------------------------------------------------------------------------
class AdminVideoJobListView(ListAPIView):
    """GET /api/v1/admin/videos?status=&current_stage= — not owner-scoped (staff-only)."""

    serializer_class = AdminVideoJobSerializer
    permission_classes = [IsSupportOrAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "current_stage"]
    pagination_class = UpdatedAtCursorPagination

    def get_queryset(self):
        return VideoJob.objects.all().select_related("user").order_by("-updated_at")


class AdminVideoJobRetryView(APIView):
    """POST /api/v1/admin/videos/{id}/retry — only from `failed`."""

    permission_classes = [IsSupportOrAdmin]

    def post(self, request, job_id):
        job = VideoJob.objects.filter(id=job_id).first()
        if job is None:
            return Response({"detail": "Video job not found."}, status=status.HTTP_404_NOT_FOUND)
        job = services.retry_job(request.user, job, request=request)
        return Response(AdminVideoJobSerializer(job).data)


class AdminVideoJobCancelView(APIView):
    """POST /api/v1/admin/videos/{id}/cancel — staff-side cancel."""

    permission_classes = [IsSupportOrAdmin]

    def post(self, request, job_id):
        job = VideoJob.objects.filter(id=job_id).first()
        if job is None:
            return Response({"detail": "Video job not found."}, status=status.HTTP_404_NOT_FOUND)
        job = services.cancel_job(request.user, job, request=request)
        return Response(AdminVideoJobSerializer(job).data)


class AdminQueuesView(APIView):
    """GET /api/v1/admin/queues (FR-85)."""

    permission_classes = [IsSupportOrAdmin]

    def get(self, request):
        return Response(services.system_health())


# ---------------------------------------------------------------------------
# Config (FR-83, FR-84)
# ---------------------------------------------------------------------------
class AdminPlanListView(ListAPIView):
    """GET /api/v1/admin/plans."""

    serializer_class = AdminPlanSerializer
    permission_classes = [IsAdmin]
    pagination_class = SortOrderCursorPagination

    def get_queryset(self):
        return Plan.objects.all().order_by("sort_order")


class AdminPlanDetailView(APIView):
    """PATCH /api/v1/admin/plans/{id} (FR-83: quota/feature config lives here, not in code)."""

    permission_classes = [IsAdmin]

    def patch(self, request, plan_id):
        from audit.services import record_audit_event

        plan = Plan.objects.filter(id=plan_id).first()
        if plan is None:
            return Response({"detail": "Plan not found."}, status=status.HTTP_404_NOT_FOUND)
        before = AdminPlanSerializer(plan).data
        serializer = AdminPlanSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_audit_event(
            actor_type="staff",
            actor_id=request.user.id,
            action="admin.plan_updated",
            resource_type="plan",
            resource_id=str(plan.id),
            request=request,
            before=before,
            after=serializer.data,
        )
        return Response(serializer.data)


class AdminProviderListView(ListAPIView):
    """GET /api/v1/admin/providers."""

    serializer_class = AdminProviderSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["service", "is_active"]
    pagination_class = ServicePriorityCursorPagination

    def get_queryset(self):
        return ApiCredentialConfig.objects.all().order_by("service", "priority")


class AdminProviderDetailView(APIView):
    """PATCH /api/v1/admin/providers/{id} (FR-84: model/priority/config, never a raw secret)."""

    permission_classes = [IsAdmin]

    def patch(self, request, provider_id):
        from audit.services import record_audit_event

        config = ApiCredentialConfig.objects.filter(id=provider_id).first()
        if config is None:
            return Response({"detail": "Provider config not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminProviderSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_audit_event(
            actor_type="staff",
            actor_id=request.user.id,
            action="admin.provider_updated",
            resource_type="api_credentials_config",
            resource_id=str(config.id),
            request=request,
            after=serializer.data,
        )
        return Response(serializer.data)


class AdminProviderRotateSecretView(APIView):
    """POST /api/v1/admin/providers/{id}/rotate-secret (C-5: only a new `secret_ref` name)."""

    permission_classes = [IsAdmin]

    def post(self, request, provider_id):
        config = ApiCredentialConfig.objects.filter(id=provider_id).first()
        if config is None:
            return Response({"detail": "Provider config not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = RotateSecretSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config = services.rotate_secret(request.user, config, serializer.validated_data["secret_ref"], request=request)
        return Response(AdminProviderSerializer(config).data)
