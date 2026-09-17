import hashlib
import tempfile
from pathlib import Path
import requests
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from rest_framework.exceptions import ValidationError
from core.storage import get_storage
from video_pipeline.models import VideoJob
from .models import TelegramArchive
from .client import call, config, secret

CHUNK_SIZE = 18 * 1024 * 1024  # Below the hosted Bot API getFile download limit.


@shared_task(
    name="telegram.archive_video",
    autoretry_for=(ValidationError,),
    retry_backoff=True,
    max_retries=3,
)
def archive_video(job_id):
    cfg = config()
    if not cfg.enabled:
        return {"status": "disabled"}
    job = VideoJob.objects.get(pk=job_id)
    if not job.final_video_s3_key or not job.moderation_approved_sha256:
        return {"status": "not_approved"}
    with transaction.atomic():
        row, _ = TelegramArchive.objects.get_or_create(
            job=job,
            defaults={
                "channel_id": cfg.channel_id,
                "checksum": job.moderation_approved_sha256,
            },
        )
        row = TelegramArchive.objects.select_for_update().get(pk=row.pk)
        if row.checksum != job.moderation_approved_sha256:
            row.checksum = job.moderation_approved_sha256
            row.parts = []
            row.status = "pending"
        if row.status == "ready" or (
            row.status == "uploading"
            and row.updated_at > timezone.now() - timedelta(minutes=15)
        ):
            return {"status": row.status}
        row.status = "uploading"
        row.save()
    try:
        with tempfile.TemporaryDirectory() as folder:
            path = get_storage().download_to(
                job.final_video_s3_key, Path(folder) / "video.mp4"
            )
            with open(path, "rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != row.checksum:
                    raise ValidationError("Video changed after moderation.")
                source.seek(0)
                index = 0
                while data := source.read(CHUNK_SIZE):
                    if index >= len(row.parts):
                        method = (
                            "sendVideo"
                            if path.stat().st_size <= CHUNK_SIZE
                            else "sendDocument"
                        )
                        field = "video" if method == "sendVideo" else "document"
                        result = call(
                            method,
                            {
                                "chat_id": row.channel_id,
                                "caption": f"Creator ID: {job.user_id}\nVideo ID: {job.pk}\nPart: {index + 1}",
                                "protect_content": "true",
                            },
                            files={
                                field: (
                                    f"{job.pk}-{index}.mp4"
                                    if field == "video"
                                    else f"{job.pk}-{index}.part",
                                    data,
                                )
                            },
                        )
                        row.parts.append(
                            {
                                "file_id": result[field]["file_id"],
                                "message_id": result["message_id"],
                                "sha256": hashlib.sha256(data).hexdigest(),
                            }
                        )
                        row.save(update_fields=["parts", "updated_at"])
                    index += 1
        row.status = "ready"
        row.error = ""
        row.save()
        return {"status": "ready"}
    except Exception:
        row.status = "failed"
        row.error = "Telegram archive failed; source remains in primary storage."
        row.save()
        raise ValidationError(row.error) from None


def restore(job):
    row = TelegramArchive.objects.filter(
        job=job, status="ready", checksum=job.moderation_approved_sha256
    ).first()
    if not row:
        raise ValidationError("Telegram archive is not ready.")
    cfg = config()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "restored.mp4"
        with path.open("wb") as output:
            for part in row.parts:
                result = call("getFile", {"file_id": part["file_id"]})
                file_path = result.get("file_path", "")
                if not file_path or ".." in file_path or "://" in file_path:
                    raise ValidationError("Invalid Telegram file path.")
                try:
                    response = requests.get(
                        f"https://api.telegram.org/file/bot{secret(cfg.token_secret_ref)}/{file_path}",
                        timeout=120,
                    )
                    response.raise_for_status()
                    data = response.content
                except requests.RequestException:
                    raise ValidationError("Telegram archive download failed.") from None
                if hashlib.sha256(data).hexdigest() != part["sha256"]:
                    raise ValidationError("Archive part checksum mismatch.")
                output.write(data)
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != row.checksum:
                raise ValidationError("Archive checksum mismatch.")
        get_storage().put_file(job.final_video_s3_key, path, content_type="video/mp4")


@shared_task(name="telegram.restore_video")
def restore_video(job_id):
    from django.core.cache import cache

    key = f"telegram-restore:{job_id}"
    try:
        restore(VideoJob.objects.get(pk=job_id))
        cache.delete(key)
    except Exception:
        cache.set(key, "failed", 60)
        raise ValidationError(
            "Telegram restore failed; retry after one minute."
        ) from None


@shared_task(name="telegram.backfill_archives")
def backfill_archives():
    if not config().enabled:
        return
    jobs = (
        VideoJob.objects.exclude(moderation_approved_sha256="")
        .exclude(final_video_s3_key="")
        .exclude(telegramarchive__status="ready")
    )
    count = 0
    for pk in jobs.values_list("pk", flat=True).iterator(chunk_size=100):
        archive_video.delay(str(pk))
        count += 1
    return {"queued": count}
