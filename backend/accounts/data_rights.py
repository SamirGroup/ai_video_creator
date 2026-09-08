"""Data-subject rights (FR-86..FR-89, SPEC 4.14 / 5.29): export, deletion,
deletion cancel. Views are thin; every side effect is a service function
below so `accounts/tasks.py` and tests share the same code path.

Deletion timeline (FR-87)
-------------------------
POST /me/data/delete   -> immediately: OAuth tokens revoked at Google and
                          hard-deleted (`channels.services.disconnect_*`),
                          non-terminal jobs canceled, all sessions revoked,
                          `users.status = pending_deletion`, notification +
                          audit. A signed cancel token (30 days) is returned
                          and included in the notification context.
<= 30 days              -> POST /me/data/delete/cancel ({token}) restores the
                          account. A pending-deletion user cannot authenticate
                          (is_active is False), hence the token.
day 30 (Beat, daily)    -> `accounts.tasks.process_due_deletions` anonymises
                          PII (see `anonymise_user`); financial rows (invoices,
                          statements, ledger) are kept untouched under the
                          anonymised user id — legal retention, FR-87.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import DataRequest, DataRequestKind, DataRequestStatus, User, UserStatus

logger = logging.getLogger("accounts.data_rights")

DELETE_CANCEL_SALT = "accounts.deletion-cancel"


def deletion_grace_days() -> int:
    return int(getattr(settings, "DATA_DELETION_GRACE_DAYS", 30))


def export_ttl_days() -> int:
    return int(getattr(settings, "DATA_EXPORT_TTL_DAYS", 7))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def request_export(user: User) -> DataRequest:
    """Create the export request and queue the zip build after commit."""
    existing = DataRequest.objects.filter(
        user=user,
        kind=DataRequestKind.EXPORT,
        status__in=[DataRequestStatus.PENDING, DataRequestStatus.PROCESSING],
    ).first()
    if existing is not None:
        return existing
    req = DataRequest.objects.create(user=user, kind=DataRequestKind.EXPORT)

    from accounts.tasks import build_data_export

    transaction.on_commit(lambda: build_data_export.delay(str(req.id)))
    logger.info("data_export_requested", extra={"user_id": str(user.pk), "request_id": str(req.id)})
    return req


def export_download_url(req: DataRequest) -> str | None:
    if req.status != DataRequestStatus.COMPLETED or not req.export_s3_key:
        return None
    if req.export_expires_at and req.export_expires_at <= timezone.now():
        return None
    from core.storage import get_storage

    remaining = int((req.export_expires_at - timezone.now()).total_seconds()) if req.export_expires_at else 3600
    return get_storage().signed_url(req.export_s3_key, expires_sec=max(60, min(remaining, 24 * 3600)))


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------
def make_deletion_cancel_token(user: User, req: DataRequest) -> str:
    return signing.dumps(
        {"user_id": str(user.pk), "request_id": str(req.id), "purpose": "deletion_cancel"},
        salt=DELETE_CANCEL_SALT,
    )


def read_deletion_cancel_token(token: str) -> tuple[str, str] | None:
    try:
        data = signing.loads(
            token, salt=DELETE_CANCEL_SALT, max_age=deletion_grace_days() * 24 * 3600
        )
    except (BadSignature, SignatureExpired):
        return None
    if data.get("purpose") != "deletion_cancel":
        return None
    return data.get("user_id"), data.get("request_id")


def _disconnect_google_accounts(user: User, request=None) -> dict:
    """FR-87 step 1: revoke + delete OAuth tokens right away. Google-side
    revoke failures are logged by `channels.services`; the local token
    columns are cleared regardless.
    """
    from channels.models import ConnectionStatus
    from channels.services import disconnect_adsense_account, disconnect_channel

    channels = 0
    for channel in user.youtube_channels.exclude(status=ConnectionStatus.DISCONNECTED):
        try:
            disconnect_channel(channel, actor_type="user", actor_id=user.pk, request=request)
        except Exception:  # pragma: no cover - never block the deletion request on Google
            logger.exception("deletion_channel_disconnect_failed", extra={"channel_id": str(channel.pk)})
            channel.access_token_enc = None
            channel.refresh_token_enc = None
            channel.status = ConnectionStatus.DISCONNECTED
            channel.disconnected_at = timezone.now()
            channel.save(update_fields=["access_token_enc", "refresh_token_enc", "status", "disconnected_at", "updated_at"])
        channels += 1
    adsense = 0
    for account in user.adsense_accounts.exclude(status=ConnectionStatus.DISCONNECTED):
        try:
            disconnect_adsense_account(account, actor_type="user", actor_id=user.pk, request=request)
        except Exception:  # pragma: no cover
            logger.exception("deletion_adsense_disconnect_failed", extra={"account_id": str(account.pk)})
            account.access_token_enc = None
            account.refresh_token_enc = None
            account.status = ConnectionStatus.DISCONNECTED
            account.save(update_fields=["access_token_enc", "refresh_token_enc", "status", "updated_at"])
        adsense += 1
    return {"channels": channels, "adsense_accounts": adsense}


def _cancel_open_jobs(user: User) -> int:
    from video_pipeline.models import JobStatus, VideoJob

    now = timezone.now()
    return VideoJob.objects.filter(user=user).exclude(
        status__in=JobStatus.terminal_statuses()
    ).update(status=JobStatus.CANCELED, completed_at=now, updated_at=now)


def request_deletion(user: User, request=None) -> tuple[DataRequest, str]:
    """FR-87: immediate token revocation, account frozen, 30-day clock started.
    Returns (request, cancel_token).
    """
    from accounts.sessions import revoke_all_sessions
    from audit.services import record_audit_event
    from notifications.services import notify

    now = timezone.now()
    with transaction.atomic():
        req = DataRequest.objects.create(
            user=user,
            kind=DataRequestKind.DELETION,
            scheduled_for=now + timedelta(days=deletion_grace_days()),
        )
        disconnected = _disconnect_google_accounts(user, request=request)
        canceled_jobs = _cancel_open_jobs(user)
        user.status = UserStatus.PENDING_DELETION
        user.save(update_fields=["status", "updated_at"])
        revoke_all_sessions(user)

        cancel_token = make_deletion_cancel_token(user, req)
        record_audit_event(
            actor_type="user",
            actor_id=user.pk,
            action="user.deletion_requested",
            resource_type="user",
            resource_id=str(user.pk),
            request=request,
            metadata={
                "request_id": str(req.id),
                "scheduled_for": req.scheduled_for.isoformat(),
                **disconnected,
                "canceled_jobs": canceled_jobs,
            },
        )
        notify(
            user,
            "data.deletion_requested",
            ctx={
                "scheduled_for": req.scheduled_for.date().isoformat(),
                "cancel_url": f"{settings.FRONTEND_BASE_URL.rstrip('/')}/account/delete/cancel?token={cancel_token}",
            },
            payload={"request_id": str(req.id)},
        )
    logger.info("data_deletion_requested", extra={"user_id": str(user.pk), "request_id": str(req.id)})
    return req, cancel_token


def cancel_deletion(user: User, req: DataRequest, request=None) -> bool:
    from audit.services import record_audit_event

    if req.kind != DataRequestKind.DELETION or req.status != DataRequestStatus.PENDING:
        return False
    if req.scheduled_for and req.scheduled_for <= timezone.now():
        return False
    with transaction.atomic():
        req.status = DataRequestStatus.CANCELED
        req.completed_at = timezone.now()
        req.save(update_fields=["status", "completed_at"])
        if user.status == UserStatus.PENDING_DELETION:
            user.status = UserStatus.ACTIVE
            user.save(update_fields=["status", "updated_at"])
        record_audit_event(
            actor_type="user",
            actor_id=user.pk,
            action="user.deletion_canceled",
            resource_type="user",
            resource_id=str(user.pk),
            request=request,
            metadata={"request_id": str(req.id)},
        )
    logger.info("data_deletion_canceled", extra={"user_id": str(user.pk), "request_id": str(req.id)})
    return True


def anonymise_user(user: User, req: DataRequest | None = None) -> dict:
    """FR-87 day-30 step. Removes/overwrites personal data, keeps financial
    truth. What is touched:

    users            email -> deleted+<uuid>@anonymised.invalid, full_name "",
                     google_sub NULL, password unusable, TOTP secret cleared,
                     marketing_opt_in False, status `deleted`, deleted_at set
    sessions         all refresh tokens blacklisted, session_meta deleted
    notifications    rows + preferences deleted
    content prefs    deleted (custom brief / brand voice are personal text)
    media            video_assets rows + objects, final video / thumbnail
                     objects, data export zips deleted from storage
    channels         title/handle/thumbnail blanked, tokens already gone
    KEPT             invoices, revenue_share_statements, ledger_entries,
                     revenue_records (aggregates), contracts, consents,
                     audit_logs, video_jobs rows (script/title text is not
                     PII; assets removed) — they now hang off an anonymised id.
    """
    from accounts.sessions import revoke_all_sessions
    from audit.services import record_audit_event
    from core.storage import get_storage
    from notifications.models import Notification, NotificationPreference
    from video_pipeline.models import VideoAsset, VideoJob

    storage = get_storage()
    removed = {"assets": 0, "objects": 0, "notifications": 0, "preferences": 0, "exports": 0}

    def _delete_object(key: str) -> None:
        if not key:
            return
        try:
            storage.delete(key)
            removed["objects"] += 1
        except Exception:  # pragma: no cover - best effort, logged
            logger.exception("anonymise_storage_delete_failed", extra={"key": key})

    with transaction.atomic():
        for asset in VideoAsset.objects.filter(job__user=user):
            _delete_object(asset.s3_key)
            removed["assets"] += 1
        VideoAsset.objects.filter(job__user=user).delete()
        for job in VideoJob.objects.filter(user=user).only("id", "final_video_s3_key", "thumbnail_s3_key"):
            _delete_object(job.final_video_s3_key)
            _delete_object(job.thumbnail_s3_key)
        VideoJob.objects.filter(user=user).update(final_video_s3_key="", thumbnail_s3_key="", preview_token="")

        for export in DataRequest.objects.filter(user=user, kind=DataRequestKind.EXPORT).exclude(export_s3_key=""):
            _delete_object(export.export_s3_key)
            removed["exports"] += 1
        DataRequest.objects.filter(user=user, kind=DataRequestKind.EXPORT).update(export_s3_key="", export_expires_at=None)

        removed["notifications"] = Notification.objects.filter(user=user).delete()[0]
        removed["preferences"] = NotificationPreference.objects.filter(user=user).delete()[0]
        user.content_preferences.all().delete()

        user.youtube_channels.update(channel_title="", channel_handle="", thumbnail_url="", access_token_enc=None, refresh_token_enc=None)
        user.adsense_accounts.update(access_token_enc=None, refresh_token_enc=None)

        revoke_all_sessions(user)
        user.session_meta.all().delete()

        user.email = f"deleted+{uuid.uuid4()}@anonymised.invalid"
        user.full_name = ""
        user.google_sub = None
        user.set_unusable_password()
        user.totp_secret_enc = None
        user.is_totp_enabled = False
        user.marketing_opt_in = False
        user.timezone = "UTC"
        user.status = UserStatus.DELETED
        user.deleted_at = timezone.now()
        user.save()

        if req is not None:
            req.status = DataRequestStatus.COMPLETED
            req.completed_at = timezone.now()
            req.save(update_fields=["status", "completed_at"])

        record_audit_event(
            actor_type="system",
            action="user.anonymised",
            resource_type="user",
            resource_id=str(user.pk),
            metadata={"request_id": str(req.id) if req else None, **removed},
        )
    logger.info("user_anonymised", extra={"user_id": str(user.pk), **removed})
    return removed


# ---------------------------------------------------------------------------
# Serializers / views
# ---------------------------------------------------------------------------
class DataRequestSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = DataRequest
        fields = [
            "id",
            "kind",
            "status",
            "requested_at",
            "scheduled_for",
            "completed_at",
            "export_expires_at",
            "rejection_reason",
            "download_url",
        ]
        read_only_fields = fields

    def get_download_url(self, obj: DataRequest) -> str | None:
        return export_download_url(obj)


class DataExportView(APIView):
    """POST /api/v1/me/data/export (FR-86)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        req = request_export(request.user)
        return Response(DataRequestSerializer(req).data, status=status.HTTP_202_ACCEPTED)


class DataExportDetailView(APIView):
    """GET /api/v1/me/data/export/{id} — owner-scoped."""

    permission_classes = [IsAuthenticated]

    def get(self, request, request_id):
        req = DataRequest.objects.filter(id=request_id, user=request.user, kind=DataRequestKind.EXPORT).first()
        if req is None:
            return Response({"detail": "Export request not found."}, status=404)
        return Response(DataRequestSerializer(req).data)


class DataDeleteView(APIView):
    """POST /api/v1/me/data/delete (FR-87)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        pending = DataRequest.objects.filter(
            user=user, kind=DataRequestKind.DELETION, status=DataRequestStatus.PENDING
        ).first()
        if pending is not None:
            return Response(
                {"detail": "A deletion request is already pending.", "request_id": str(pending.id)},
                status=status.HTTP_409_CONFLICT,
            )
        req, cancel_token = request_deletion(user, request=request)
        data = DataRequestSerializer(req).data
        data["cancel_token"] = cancel_token
        return Response(data, status=status.HTTP_202_ACCEPTED)


class DeletionCancelSerializer(serializers.Serializer):
    token = serializers.CharField(required=False, allow_blank=True)


class DataDeleteCancelView(APIView):
    """POST /api/v1/me/data/delete/cancel — within the 30-day grace period.

    Accepts the signed `token` from the deletion response / notification
    (the account is inactive meanwhile, so a JWT cannot be presented) or, for
    an account that is still active, the current authentication.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = DeletionCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data.get("token") or ""

        user = None
        req = None
        if token:
            parsed = read_deletion_cancel_token(token)
            if parsed is None:
                return Response({"detail": "Invalid or expired cancel token."}, status=400)
            user_id, request_id = parsed
            user = User.objects.filter(pk=user_id).first()
            req = DataRequest.objects.filter(id=request_id, user=user).first() if user else None
        elif request.user and request.user.is_authenticated:
            user = request.user
            req = DataRequest.objects.filter(
                user=user, kind=DataRequestKind.DELETION, status=DataRequestStatus.PENDING
            ).first()
        else:
            return Response({"detail": "Authentication credentials were not provided."}, status=401)

        if user is None or req is None or not cancel_deletion(user, req, request=request):
            return Response({"detail": "No cancellable deletion request found."}, status=status.HTTP_409_CONFLICT)
        return Response(DataRequestSerializer(req).data)
