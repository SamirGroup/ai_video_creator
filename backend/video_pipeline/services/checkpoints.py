"""FR-43 stage checkpoints: every stage artifact goes to object storage and is
recorded in `video_assets`, so a retried or resumed job never redoes finished work.

`existing_asset()` is the skip test each stage runs first: the row must exist
*and* the object must still be in storage (lifecycle rules delete raw assets
after 30 days, A-18). A row whose object is gone is treated as "no checkpoint"
and the stage regenerates it.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from core.storage import get_storage, job_asset_key
from video_pipeline.models import VideoAsset

logger = logging.getLogger("video_pipeline.checkpoints")


def existing_asset(job, kind: str, *, sequence_index: int | None = None) -> VideoAsset | None:
    """Return the checkpoint row for `(job, kind[, sequence_index])` if its object exists."""
    asset = (
        VideoAsset.objects.filter(job=job, kind=kind, sequence_index=sequence_index)
        .order_by("-created_at")
        .first()
    )
    if asset is None or not asset.s3_key:
        return None
    try:
        if not get_storage().exists(asset.s3_key):
            logger.warning(
                "checkpoint_object_missing",
                extra={"job_id": str(job.pk), "kind": kind, "s3_key": asset.s3_key},
            )
            return None
    except Exception:  # storage outage: behave as if no checkpoint, the stage will retry
        logger.exception("checkpoint_exists_check_failed", extra={"job_id": str(job.pk), "kind": kind})
        return None
    return asset


def asset_key(job, kind: str, filename: str) -> str:
    return job_asset_key(job.pk, kind, filename)


def store_file_asset(
    job,
    kind: str,
    path: str | os.PathLike,
    *,
    filename: str | None = None,
    mime_type: str = "",
    duration_ms: int | None = None,
    provider: str = "",
    sequence_index: int | None = None,
    metadata: dict | None = None,
    license_ref: str = "",
) -> VideoAsset:
    """Upload a local file and upsert its `video_assets` row (one row per
    `(job, kind, sequence_index)` — a re-run replaces, never duplicates).
    """
    path = Path(path)
    key = asset_key(job, kind, filename or path.name)
    stored = get_storage().put_file(key, path, content_type=mime_type)
    return _upsert_asset(
        job,
        kind,
        key=stored.key,
        mime_type=stored.content_type,
        size_bytes=stored.size_bytes,
        checksum=stored.checksum_sha256,
        duration_ms=duration_ms,
        provider=provider,
        sequence_index=sequence_index,
        metadata=metadata,
        license_ref=license_ref,
    )


def store_bytes_asset(
    job,
    kind: str,
    data: bytes,
    *,
    filename: str,
    mime_type: str = "",
    duration_ms: int | None = None,
    provider: str = "",
    sequence_index: int | None = None,
    metadata: dict | None = None,
    license_ref: str = "",
) -> VideoAsset:
    key = asset_key(job, kind, filename)
    stored = get_storage().put_bytes(key, data, content_type=mime_type)
    return _upsert_asset(
        job,
        kind,
        key=stored.key,
        mime_type=stored.content_type,
        size_bytes=stored.size_bytes,
        checksum=stored.checksum_sha256,
        duration_ms=duration_ms,
        provider=provider,
        sequence_index=sequence_index,
        metadata=metadata,
        license_ref=license_ref,
    )


def _upsert_asset(
    job,
    kind: str,
    *,
    key: str,
    mime_type: str,
    size_bytes: int,
    checksum: str,
    duration_ms: int | None,
    provider: str,
    sequence_index: int | None,
    metadata: dict | None,
    license_ref: str,
) -> VideoAsset:
    asset, _created = VideoAsset.objects.update_or_create(
        job=job,
        kind=kind,
        sequence_index=sequence_index,
        defaults={
            "s3_key": key,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "duration_ms": duration_ms,
            "checksum_sha256": checksum,
            "provider": provider,
            "license_ref": license_ref,
            "metadata": metadata or {},
        },
    )
    logger.info(
        "checkpoint_stored",
        extra={
            "job_id": str(job.pk),
            "kind": kind,
            "sequence_index": sequence_index,
            "size_bytes": size_bytes,
        },
    )
    return asset


def download_asset(asset: VideoAsset, dest: str | os.PathLike) -> Path:
    return get_storage().download_to(asset.s3_key, dest)


def drop_assets(job, kinds: list[str]) -> int:
    """Delete checkpoint rows (and their objects, best effort) for a regeneration
    that restarts before those stages (FR-39 "request changes").
    """
    storage = get_storage()
    removed = 0
    for asset in VideoAsset.objects.filter(job=job, kind__in=kinds):
        if asset.s3_key:
            try:
                storage.delete(asset.s3_key)
            except Exception:  # object already gone / storage hiccup — the row is what matters
                logger.warning(
                    "checkpoint_delete_failed", extra={"job_id": str(job.pk), "s3_key": asset.s3_key}
                )
        asset.delete()
        removed += 1
    return removed
