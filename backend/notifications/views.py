from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import Notification, NotificationPreference
from notifications.serializers import NotificationPreferenceSerializer, NotificationSerializer


class NotificationListView(ListAPIView):
    """GET /api/v1/notifications."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")


class MarkNotificationReadView(APIView):
    """POST /api/v1/notifications/{id}/read."""

    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):
        notification = Notification.objects.filter(id=notification_id, user=request.user).first()
        if notification is None:
            return Response({"detail": "Notification not found."}, status=404)
        if notification.status != "read":
            notification.status = "read"
            notification.read_at = timezone.now()
            notification.save(update_fields=["status", "read_at"])
        return Response(NotificationSerializer(notification).data)


class MarkAllNotificationsReadView(APIView):
    """POST /api/v1/notifications/read-all."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(user=request.user).exclude(status="read").update(
            status="read", read_at=timezone.now()
        )
        return Response({"updated": updated})


class NotificationPreferencesView(APIView):
    """GET/PATCH /api/v1/notifications/preferences (FR-76 — transactional/security
    notifications are excluded from this list and can never be disabled).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        preferences = NotificationPreference.objects.filter(user=request.user)
        return Response(NotificationPreferenceSerializer(preferences, many=True).data)

    def patch(self, request):
        return Response(
            {"detail": "Bulk preference update is not implemented yet."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
