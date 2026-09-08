"""Celery tasks for identity / data-rights work (FR-86, FR-87, FR-89).

* `build_data_export`             — on demand, builds the FR-86 zip.
* `process_due_deletions`         — Beat, daily: anonymise accounts whose
                                    30-day grace period elapsed (FR-87).
* `purge_disconnected_channel_data` — Beat, daily: FR-89 — 30 days after a
                                    channel was disconnected, drop the raw
                                    YouTube/AdSense data we still hold.

Beat entries are registered in `config/settings/base.py` (Track E block).
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from accounts.models import DataRequest, DataRequestKind, DataRequestStatus, User, UserStatus

logger = logging.getLogger("accounts.tasks")

# Column whitelists: an export must never carry a secret, so every table is
# serialised through an explicit field list (no `values()` of everything).
_FORBIDDEN_FIELD_FRAGMENTS = ("token", "secret", "password", "_enc")


def _rows(queryset, fields: list[str]) -> list[dict]:
    for field in fields:
        lowered = field.lower()
        if any(fragment in lowered for fragment in _FORBIDDEN_FIELD_FRAGMENTS):
            raise ValueError(f"Refusing to export sensitive column {field!r}")
    return [dict(row) for row in queryset.values(*fields)]


def collect_user_data(user: User) -> tuple[dict, list[dict]]:
    """Return (data, media_manifest). Pure read; storage is not touched."""
    from contracts.models import Contract
    from notifications.models import Notification, NotificationPreference
    from revenue.models import Invoice, RevenueShareStatement
    from video_pipeline.models import VideoAsset, VideoJob

    data: dict = {
        "format_version": "1.0",
        "generated_at": timezone.now().isoformat(),
        "profile": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "locale": user.locale,
            "timezone": user.timezone,
            "status": user.status,
            "is_email_verified": user.is_email_verified,
            "marketing_opt_in": user.marketing_opt_in,
            "is_totp_enabled": user.is_totp_enabled,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
            "roles": list(user.user_roles.values_list("role__code", flat=True)),
        },
        "youtube_channels": _rows(
            user.youtube_channels.all(),
            [
                "id", "youtube_channel_id", "channel_title", "channel_handle", "thumbnail_url",
                "subscriber_count", "video_count", "is_monetized", "monetization_source",
                "granted_scopes", "status", "connected_at", "disconnected_at", "last_synced_at",
            ],
        ),
        "adsense_accounts": _rows(
            user.adsense_accounts.all(),
            ["id", "adsense_account_id", "granted_scopes", "status", "connected_at", "last_synced_at"],
        ),
        "content_preferences": _rows(
            user.content_preferences.all(),
            [
                "id", "channel_id", "niche", "custom_brief", "brand_voice", "banned_topics", "language",
                "video_duration_sec", "aspect_ratio", "frequency", "publish_time_local", "publish_timezone",
                "publish_days", "youtube_privacy_status", "youtube_category_id", "made_for_kids",
                "approval_mode", "auto_publish_on_timeout", "voice_id", "music_style", "is_paused", "created_at",
            ],
        ),
        "notification_preferences": _rows(
            NotificationPreference.objects.filter(user=user),
            ["type", "email_enabled", "in_app_enabled", "push_enabled"],
        ),
        "video_jobs": _rows(
            VideoJob.objects.filter(user=user),
            [
                "id", "channel_id", "trigger", "status", "current_stage", "scheduled_for", "title",
                "description", "tags", "script_text", "language", "duration_sec", "approval_requested_at",
                "approved_at", "rejected_at", "rejection_reason", "youtube_video_id", "youtube_url",
                "published_at", "error_code", "retry_count", "total_cost_usd", "created_at", "completed_at",
            ],
        ),
        "revenue_share_statements": _rows(
            RevenueShareStatement.objects.filter(user=user),
            [
                "id", "period_start", "period_end", "currency", "gross_revenue", "platform_share_pct",
                "platform_share_amount", "creator_share_amount", "video_count", "status", "finalized_at",
                "disputed_at", "dispute_reason", "created_at",
            ],
        ),
        "invoices": _rows(
            Invoice.objects.filter(user=user),
            ["id", "kind", "amount", "currency", "status", "due_at", "paid_at", "created_at"],
        ),
        "contracts": _rows(
            Contract.objects.filter(user=user),
            [
                "id", "contract_version__version", "signed_at", "body_sha256", "consent_revenue_share",
                "consent_publish_to_channel", "consent_data_processing", "consent_marketing", "status",
                "terminated_at",
            ],
        ),
        "notifications": _rows(
            Notification.objects.filter(user=user),
            ["id", "type", "channel", "title", "body", "status", "sent_at", "read_at", "created_at"],
        ),
        "data_requests": _rows(
            DataRequest.objects.filter(user=user),
            ["id", "kind", "status", "requested_at", "scheduled_for", "completed_at", "export_expires_at"],
        ),
    }
    try:
        from accounts.models import Consent  # Track A model, may not exist yet

        data["consents"] = _rows(
            Consent.objects.filter(user=user),
            ["id", "consent_type", "granted", "scope_details", "granted_at", "revoked_at"],
        )
    except ImportError:  # pragma: no cover
        data["consents"] = []

    manifest: list[dict] = []
    for asset in VideoAsset.objects.filter(job__user=user).values(
        "job_id", "kind", "s3_key", "mime_type", "size_bytes", "duration_ms", "checksum_sha256", "created_at"
    ):
        manifest.append({**asset, "job_id": str(asset["job_id"])})
    for job in VideoJob.objects.filter(user=user).exclude(final_video_s3_key="").values(
        "id", "final_video_s3_key", "thumbnail_s3_key"
    ):
        manifest.append({"job_id": str(job["id"]), "kind": "final_video", "s3_key": job["final_video_s3_key"]})
        if job["thumbnail_s3_key"]:
            manifest.append({"job_id": str(job["id"]), "kind": "thumbnail", "s3_key": job["thumbnail_s3_key"]})
    for contract in Contract.objects.filter(user=user).exclude(pdf_s3_key="").values("id", "pdf_s3_key"):
        manifest.append({"contract_id": str(contract["id"]), "kind": "contract_pdf", "s3_key": contract["pdf_s3_key"]})
    return data, manifest


def build_export_zip(user: User) -> bytes:
    data, manifest = collect_user_data(user)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.json", json.dumps(data, indent=2, default=str, ensure_ascii=False))
        archive.writestr(
            "media_manifest.json",
            json.dumps(
                {
                    "note": "Object keys only. Ask support for time-limited download links; "
                    "no signed URLs are embedded so the archive can be shared safely.",
                    "objects": manifest,
                },
                indent=2,
                default=str,
            ),
        )
        archive.writestr(
            "README.txt",
            "Data export generated by AI YouTube Content Ecosystem (FR-86).\n"
            "data.json — your profile, channels (metadata only, never OAuth tokens),\n"
            "preferences, video jobs, statements, invoices, consents, notifications.\n"
            "media_manifest.json — storage keys of your generated media.\n",
        )
    return buffer.getvalue()


@shared_task(bind=True, queue="celery", max_retries=2, acks_late=True)
def build_data_export(self, request_id: str):
    """FR-86: build the zip, store it under `exports/<user>/<request>.zip`,
    notify the creator with a 7-day signed link.
    """
    from core.storage import data_export_key, get_storage
    from notifications.services import notify

    req = DataRequest.objects.select_related("user").filter(pk=request_id, kind=DataRequestKind.EXPORT).first()
    if req is None:
        logger.warning("data_export_request_missing", extra={"request_id": request_id})
        return {"request_id": request_id, "status": "missing"}
    if req.status == DataRequestStatus.COMPLETED:
        return {"request_id": request_id, "status": req.status, "skipped": True}

    req.status = DataRequestStatus.PROCESSING
    req.save(update_fields=["status"])
    user = req.user
    try:
        payload = build_export_zip(user)
        key = data_export_key(user.pk, req.pk)
        storage = get_storage()
        storage.put_bytes(key, payload, content_type="application/zip")
        ttl_days = int(getattr(settings, "DATA_EXPORT_TTL_DAYS", 7))
        req.export_s3_key = key
        req.export_expires_at = timezone.now() + timedelta(days=ttl_days)
        req.status = DataRequestStatus.COMPLETED
        req.completed_at = timezone.now()
        req.save(update_fields=["export_s3_key", "export_expires_at", "status", "completed_at"])
        url = storage.signed_url(key, expires_sec=ttl_days * 24 * 3600)
        notify(user, "data.export_ready", ctx={"url": url}, payload={"request_id": str(req.id)})
    except Exception as exc:
        req.status = DataRequestStatus.FAILED
        req.error = str(exc)[:2000]
        req.save(update_fields=["status", "error"])
        logger.exception("data_export_failed", extra={"request_id": request_id})
        raise
    logger.info("data_export_completed", extra={"request_id": request_id, "user_id": str(user.pk), "bytes": len(payload)})
    return {"request_id": request_id, "status": req.status, "bytes": len(payload)}


@shared_task(queue="celery")
def process_due_deletions() -> dict:
    """FR-87 day-30: anonymise every account whose deletion grace period
    ended and which was not canceled in the meantime.
    """
    from accounts.data_rights import anonymise_user

    now = timezone.now()
    due = DataRequest.objects.select_related("user").filter(
        kind=DataRequestKind.DELETION,
        status=DataRequestStatus.PENDING,
        scheduled_for__lte=now,
        user__status=UserStatus.PENDING_DELETION,
    )
    processed, failed = 0, 0
    for req in due:
        try:
            anonymise_user(req.user, req)
            processed += 1
        except Exception:
            failed += 1
            logger.exception("deletion_anonymise_failed", extra={"request_id": str(req.id)})
    logger.info("deletions_processed", extra={"processed": processed, "failed": failed})
    return {"processed": processed, "failed": failed}


@shared_task(queue="celery")
def purge_disconnected_channel_data() -> dict:
    """FR-89: 30 days after a channel is disconnected/revoked, remove the
    YouTube-derived data that is not needed for the financial record.

    Removed
      youtube_channels   channel_title, channel_handle, thumbnail_url,
                         subscriber_count, video_count, granted_scopes,
                         last_error_code (tokens were already hard-deleted at
                         disconnect time, FR-15)
      revenue_records    raw_payload (the verbatim Analytics/AdSense response)
    Kept
      revenue_records    aggregated figures (views, revenue, cpm/rpm, date) —
                         they feed statements/invoices and are retained under
                         FR-87's financial-records exception
      video_jobs         youtube_video_id / youtube_url (publication proof
                         referenced by revenue_records and statements)
    """
    from audit.services import record_audit_event
    from channels.models import ConnectionStatus, YouTubeChannel
    from revenue.models import RevenueRecord

    days = int(getattr(settings, "CHANNEL_DATA_PURGE_DAYS", 30))
    cutoff = timezone.now() - timedelta(days=days)
    stale = YouTubeChannel.objects.filter(
        status__in=[ConnectionStatus.DISCONNECTED, ConnectionStatus.REVOKED],
        disconnected_at__isnull=False,
        disconnected_at__lte=cutoff,
    ).filter(
        ~Q(channel_title="")
        | ~Q(channel_handle="")
        | ~Q(thumbnail_url="")
        | Q(subscriber_count__isnull=False)
        | Q(video_count__isnull=False)
        | ~Q(granted_scopes=[])
    )
    purged = 0
    for channel in stale:
        payloads_cleared = RevenueRecord.objects.filter(channel=channel).exclude(raw_payload={}).update(raw_payload={})
        channel.channel_title = ""
        channel.channel_handle = ""
        channel.thumbnail_url = ""
        channel.subscriber_count = None
        channel.video_count = None
        channel.granted_scopes = []
        channel.last_error_code = ""
        channel.access_token_enc = None
        channel.refresh_token_enc = None
        channel.save()
        record_audit_event(
            actor_type="system",
            action="channel.data_purged",
            resource_type="youtube_channel",
            resource_id=str(channel.pk),
            metadata={"raw_payloads_cleared": payloads_cleared, "after_days": days},
        )
        purged += 1
    # Revenue payloads of channels purged on an earlier run but synced since.
    late_payloads = RevenueRecord.objects.filter(
        channel__status__in=[ConnectionStatus.DISCONNECTED, ConnectionStatus.REVOKED],
        channel__disconnected_at__lte=cutoff,
    ).exclude(raw_payload={}).update(raw_payload={})
    logger.info("disconnected_channel_data_purged", extra={"channels": purged, "late_payloads": late_payloads})
    return {"channels": purged, "raw_payloads": late_payloads}
