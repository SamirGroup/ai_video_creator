from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from content_planning import services
from content_planning.serializers import ContentPreferenceReadSerializer, ContentPreferenceSerializer


class ContentPreferenceView(APIView):
    """GET / POST / PATCH /api/v1/channels/{id}/preferences (FR-33, FR-34). Owner-scoped."""

    permission_classes = [IsAuthenticated]

    def get(self, request, channel_id):
        channel = services.get_owned_channel(request.user, channel_id)
        pref = services.get_preference(channel)
        if pref is None:
            raise NotFound("No content preferences for this channel yet.")
        return Response(ContentPreferenceReadSerializer(pref).data)

    def post(self, request, channel_id):
        channel = services.get_owned_channel(request.user, channel_id)
        serializer = ContentPreferenceSerializer(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        pref = services.create_preference(request.user, channel, serializer.validated_data, request=request)
        return Response(ContentPreferenceReadSerializer(pref).data, status=status.HTTP_201_CREATED)

    def patch(self, request, channel_id):
        channel = services.get_owned_channel(request.user, channel_id)
        pref = services.get_preference(channel)
        if pref is None:
            raise NotFound("No content preferences for this channel yet.")
        serializer = ContentPreferenceSerializer(pref, data=request.data, partial=True, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        pref = services.update_preference(pref, serializer.validated_data, request=request)
        return Response(ContentPreferenceReadSerializer(pref).data)


class _PauseResumeBase(APIView):
    permission_classes = [IsAuthenticated]
    paused: bool = True

    def post(self, request, channel_id):
        channel = services.get_owned_channel(request.user, channel_id)
        pref = services.get_preference(channel)
        if pref is None:
            raise NotFound("No content preferences for this channel yet.")
        if self.paused:
            pref = services.pause_preference(pref, request=request)
        else:
            pref = services.resume_preference(pref, request=request)
        return Response(ContentPreferenceReadSerializer(pref).data)


class PausePreferenceView(_PauseResumeBase):
    """POST /api/v1/channels/{id}/preferences/pause (FR-36)."""

    paused = True


class ResumePreferenceView(_PauseResumeBase):
    """POST /api/v1/channels/{id}/preferences/resume (FR-36)."""

    paused = False
