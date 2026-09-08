"""Object storage abstraction (SPEC 9 "AWS S3 / GCP Storage", NFR-7, FR-43).

Two backends behind one tiny interface:

* `S3Storage`  — boto3 against a **private** bucket (never public-read). Signed
  GET URLs default to 24h (NFR-7). `AWS_S3_ENDPOINT_URL` lets dev point at MinIO.
* `LocalFileStorage` — files under `LOCAL_MEDIA_ROOT`; "signed URL" is a
  `TimestampSigner`-signed token served by `core.views.serve_local_media`.
  Used automatically when `AWS_STORAGE_BUCKET_NAME` is empty so tests, CI and a
  single-machine dev run need no cloud credentials (ARCHITECTURE D-6).

Callers never build S3 keys ad hoc — use the `*_key()` helpers so the layout in
ARCHITECTURE section 6 stays consistent and lifecycle rules apply.
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

logger = logging.getLogger("core.storage")

DEFAULT_SIGNED_URL_TTL_SEC = 24 * 60 * 60  # NFR-7


# ---------------------------------------------------------------------------
# Key layout helpers (ARCHITECTURE section 6)
# ---------------------------------------------------------------------------
def job_asset_key(job_id, kind: str, filename: str) -> str:
    return f"jobs/{job_id}/{kind}/{filename}"


def contract_pdf_key(user_id, contract_id) -> str:
    return f"contracts/{user_id}/{contract_id}.pdf"


def statement_pdf_key(user_id, statement_id) -> str:
    return f"statements/{user_id}/{statement_id}.pdf"


def data_export_key(user_id, request_id) -> str:
    return f"exports/{user_id}/{request_id}.zip"


def sha256_of_file(path: str | os.PathLike) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class StoredObject:
    key: str
    size_bytes: int
    content_type: str
    checksum_sha256: str


class Storage(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str = "") -> StoredObject: ...
    def put_file(self, key: str, path: str | os.PathLike, content_type: str = "") -> StoredObject: ...
    def get_bytes(self, key: str) -> bytes: ...
    def download_to(self, key: str, path: str | os.PathLike) -> Path: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def signed_url(self, key: str, expires_sec: int = DEFAULT_SIGNED_URL_TTL_SEC) -> str: ...


def _guess_content_type(key: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    guessed, _ = mimetypes.guess_type(key)
    return guessed or "application/octet-stream"


# ---------------------------------------------------------------------------
# Local filesystem backend
# ---------------------------------------------------------------------------
class LocalFileStorage:
    """Dev/test backend. Not for production (no lifecycle, no replication)."""

    def __init__(self, root: str | os.PathLike | None = None):
        self.root = Path(root or settings.LOCAL_MEDIA_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        self._signer = TimestampSigner(salt="core.storage.local")

    def _path(self, key: str) -> Path:
        safe = Path(key)
        if safe.is_absolute() or ".." in safe.parts:
            raise ValueError(f"Unsafe storage key: {key!r}")
        return self.root / safe

    def put_bytes(self, key: str, data: bytes, content_type: str = "") -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredObject(
            key=key,
            size_bytes=len(data),
            content_type=_guess_content_type(key, content_type),
            checksum_sha256=sha256_of_bytes(data),
        )

    def put_file(self, key: str, src: str | os.PathLike, content_type: str = "") -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, path)
        return StoredObject(
            key=key,
            size_bytes=path.stat().st_size,
            content_type=_guess_content_type(key, content_type),
            checksum_sha256=sha256_of_file(path),
        )

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def download_to(self, key: str, dest: str | os.PathLike) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._path(key), dest)
        return dest

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def signed_url(self, key: str, expires_sec: int = DEFAULT_SIGNED_URL_TTL_SEC) -> str:
        token = self._signer.sign(key)
        base = settings.BACKEND_BASE_URL.rstrip("/")
        return f"{base}/internal/media/?token={token}&ttl={int(expires_sec)}"

    def resolve_signed_token(self, token: str, ttl: int) -> Path:
        """Used by `core.views.serve_local_media`. Raises on bad/expired token."""
        try:
            key = self._signer.unsign(token, max_age=ttl)
        except (BadSignature, SignatureExpired) as exc:
            raise PermissionError("Invalid or expired media token.") from exc
        return self._path(key)


# ---------------------------------------------------------------------------
# S3 backend
# ---------------------------------------------------------------------------
class S3Storage:
    def __init__(self, bucket: str | None = None):
        import boto3  # imported lazily so local runs never need boto3 configured

        self.bucket = bucket or settings.AWS_STORAGE_BUCKET_NAME
        session_kwargs = {"region_name": settings.AWS_S3_REGION_NAME}
        if settings.AWS_STORAGE_ACCESS_KEY_ID:
            session_kwargs["aws_access_key_id"] = settings.AWS_STORAGE_ACCESS_KEY_ID
            session_kwargs["aws_secret_access_key"] = settings.AWS_STORAGE_SECRET_ACCESS_KEY
        client_kwargs = {}
        if settings.AWS_S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = settings.AWS_S3_ENDPOINT_URL
        self.client = boto3.session.Session(**session_kwargs).client("s3", **client_kwargs)

    def put_bytes(self, key: str, data: bytes, content_type: str = "") -> StoredObject:
        ct = _guess_content_type(key, content_type)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=ct)
        return StoredObject(key=key, size_bytes=len(data), content_type=ct, checksum_sha256=sha256_of_bytes(data))

    def put_file(self, key: str, src: str | os.PathLike, content_type: str = "") -> StoredObject:
        ct = _guess_content_type(key, content_type)
        self.client.upload_file(str(src), self.bucket, key, ExtraArgs={"ContentType": ct})
        return StoredObject(
            key=key,
            size_bytes=Path(src).stat().st_size,
            content_type=ct,
            checksum_sha256=sha256_of_file(src),
        )

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def download_to(self, key: str, dest: str | os.PathLike) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(dest))
        return dest

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_url(self, key: str, expires_sec: int = DEFAULT_SIGNED_URL_TTL_SEC) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=int(expires_sec)
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
_storage: Storage | None = None


def get_storage() -> Storage:
    """Process-wide storage singleton. `reset_storage()` exists for tests that
    override settings.
    """
    global _storage
    if _storage is None:
        if settings.AWS_STORAGE_BUCKET_NAME:
            _storage = S3Storage()
            logger.info("storage_backend_selected", extra={"backend": "s3"})
        else:
            _storage = LocalFileStorage()
            logger.info("storage_backend_selected", extra={"backend": "local", "root": str(_storage.root)})
    return _storage


def reset_storage() -> None:
    global _storage
    _storage = None


def open_upload(fh: BinaryIO) -> bytes:
    """Small helper for views receiving uploaded files."""
    return fh.read()
