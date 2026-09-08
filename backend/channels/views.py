"""SPEC 6 "OAuth (Google)" and "Channels" groups.

Real Google OAuth 2.0 (authorization code + PKCE) via `google-auth-oauthlib`
and `google-api-python-client` — no browser automation, no credential
handling, no account creation on Google's side (C-1, C-2). All Google-facing
calls and DB side-effects live in `channels/services.py`; these views stay
thin request/response glue.
"""
from __future__ import annotations

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record_audit_event
from channels import services
from channels.models import AdSenseAccount, ConnectionStatus, YouTubeChannel
from channels.serializers import AdSenseAccountSerializer, YouTubeChannelSerializer

logger = logging.getLogger("channels.views")


class YouTubeChannelListView(ListAPIView):
    """GET /api/v1/channels."""

    serializer_class = YouTubeChannelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return YouTubeChannel.objects.filter(user=self.request.user, deleted_at__isnull=True)


class YouTubeChannelDetailView(APIView):
    """GET/DELETE /api/v1/channels/{id} — object-level scoped to the owner (no IDOR)."""

    permission_classes = [IsAuthenticated]

    def _get_owned_channel(self, request, channel_id):
        return YouTubeChannel.objects.filter(
            id=channel_id, user=request.user, deleted_at__isnull=True
        ).first()

    def get(self, request, channel_id):
        channel = self._get_owned_channel(request, channel_id)
        if channel is None:
            return Response({"detail": "Channel not found."}, status=404)
        return Response(YouTubeChannelSerializer(channel).data)

    def delete(self, request, channel_id):
        """FR-15: revoke at Google, hard-delete stored tokens, audit log."""
        channel = self._get_owned_channel(request, channel_id)
        if channel is None:
            return Response({"detail": "Channel not found."}, status=404)
        services.disconnect_channel(channel, actor_type="user", actor_id=request.user.id, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class YouTubeOAuthAuthorizeView(APIView):
    """GET /api/v1/oauth/youtube/authorize (FR-10, FR-11, NFR-4).

    Returns the Google authorization URL for the frontend to redirect the
    creator to (access_type=offline, prompt=consent, PKCE S256, one-time
    `state` with a 10 minute TTL).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        authorization_url, state = services.build_authorization_request(
            kind="youtube",
            user_id=request.user.id,
            scopes=services.YOUTUBE_SCOPES,
            redirect_uri=settings.GOOGLE_OAUTH_REDIRECT_URI,
        )
        return Response({"authorization_url": authorization_url, "state": state})


class YouTubeOAuthCallbackView(APIView):
    """GET /api/v1/oauth/youtube/callback (FR-12, FR-13, FR-16, FR-17)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        error = request.query_params.get("error")
        if error:
            return Response({"detail": f"Google denied the request: {error}"}, status=400)

        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or not state:
            return Response({"detail": "Missing code or state."}, status=400)

        try:
            pending = services.consume_oauth_state(kind="youtube", state=state, user_id=request.user.id)
        except services.OAuthStateError as exc:
            return Response({"detail": str(exc)}, status=400)

        try:
            credentials = services.exchange_code_for_credentials(code=code, pending=pending)
            channel_payload = services.fetch_own_channel(credentials)
            channel, created = services.persist_youtube_channel(
                user=request.user,
                credentials=credentials,
                channel_payload=channel_payload,
                granted_scopes=pending.scopes,
            )
        except services.ChannelAlreadyLinkedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except services.OAuthExchangeError as exc:
            logger.warning(
                "youtube_oauth_callback_failed",
                extra={"user_id": str(request.user.id), "error": str(exc)},
            )
            return Response({"detail": f"Could not connect YouTube channel: {exc}"}, status=400)

        record_audit_event(
            actor_type="user",
            actor_id=request.user.id,
            action="oauth.granted",
            resource_type="youtube_channel",
            resource_id=str(channel.id),
            request=request,
            after={"scopes": pending.scopes, "youtube_channel_id": channel.youtube_channel_id},
        )
        return Response(
            YouTubeChannelSerializer(channel).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class YouTubeOAuthRevokeView(APIView):
    """POST /api/v1/oauth/youtube/revoke (FR-15)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        channel = YouTubeChannel.objects.filter(
            user=request.user, deleted_at__isnull=True, access_token_enc__isnull=False
        ).first()
        if channel is None:
            return Response({"detail": "No connected YouTube channel."}, status=404)
        services.disconnect_channel(channel, actor_type="user", actor_id=request.user.id, request=request)
        return Response({"detail": "YouTube channel disconnected."})


class AdSenseOAuthAuthorizeView(APIView):
    """GET /api/v1/oauth/adsense/authorize (FR-19) — same PKCE pattern as YouTube,
    independent consent, scope `adsense.readonly` only.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        authorization_url, state = services.build_authorization_request(
            kind="adsense",
            user_id=request.user.id,
            scopes=services.ADSENSE_SCOPES,
            redirect_uri=settings.GOOGLE_ADSENSE_REDIRECT_URI,
        )
        return Response({"authorization_url": authorization_url, "state": state})


class AdSenseOAuthCallbackView(APIView):
    """GET /api/v1/oauth/adsense/callback (FR-19, FR-20)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        error = request.query_params.get("error")
        if error:
            return Response({"detail": f"Google denied the request: {error}"}, status=400)

        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or not state:
            return Response({"detail": "Missing code or state."}, status=400)

        try:
            pending = services.consume_oauth_state(kind="adsense", state=state, user_id=request.user.id)
        except services.OAuthStateError as exc:
            return Response({"detail": str(exc)}, status=400)

        try:
            credentials = services.exchange_code_for_credentials(code=code, pending=pending)
            account_payload = services.fetch_adsense_account(credentials)
            account, created = services.persist_adsense_account(
                user=request.user,
                credentials=credentials,
                account_payload=account_payload,
                granted_scopes=pending.scopes,
            )
        except services.ChannelAlreadyLinkedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except services.OAuthExchangeError as exc:
            return Response({"detail": f"Could not connect AdSense account: {exc}"}, status=400)

        record_audit_event(
            actor_type="user",
            actor_id=request.user.id,
            action="oauth.granted",
            resource_type="adsense_account",
            resource_id=str(account.id),
            request=request,
            after={"scopes": pending.scopes},
        )
        return Response(
            AdSenseAccountSerializer(account).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AdSenseOAuthRevokeView(APIView):
    """POST /api/v1/oauth/adsense/revoke."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        account = AdSenseAccount.objects.filter(
            user=request.user, deleted_at__isnull=True, access_token_enc__isnull=False
        ).first()
        if account is None:
            return Response({"detail": "No connected AdSense account."}, status=404)
        services.disconnect_adsense_account(account, actor_type="user", actor_id=request.user.id, request=request)
        return Response({"detail": "AdSense account disconnected."})


class YouTubeChannelSyncView(APIView):
    """POST /api/v1/channels/{id}/sync — refreshes subscriber/video counts."""

    permission_classes = [IsAuthenticated]

    def post(self, request, channel_id):
        channel = YouTubeChannel.objects.filter(
            id=channel_id, user=request.user, deleted_at__isnull=True
        ).first()
        if channel is None:
            return Response({"detail": "Channel not found."}, status=404)
        if channel.status != ConnectionStatus.CONNECTED:
            return Response({"detail": "Channel is not connected."}, status=409)
        try:
            updated = services.sync_channel_metadata(channel)
        except services.OAuthExchangeError as exc:
            return Response({"detail": f"Sync failed: {exc}"}, status=502)
        return Response(YouTubeChannelSerializer(updated).data)
