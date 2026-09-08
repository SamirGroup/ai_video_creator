"""Field-level encryption helpers (NFR-2, C-5): OAuth tokens and TOTP secrets are
encrypted at the application layer before they ever reach PostgreSQL, using Fernet
(AES-128-CBC + HMAC-SHA256 authenticated encryption from the `cryptography` package).

Key material comes from `FIELD_ENCRYPTION_KEYS` (see backend/.env.example):
    "<version>:<key>,<version>:<key>,..."
The first entry is the active key used for new encryptions; all configured keys are
tried on decrypt, which is how key rotation works (`MultiFernet`).
"""
from __future__ import annotations

import warnings

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

__all__ = ["encrypt_value", "decrypt_value", "InvalidToken", "get_active_key_version"]

_multi_fernet: MultiFernet | None = None
_active_key_version: int = 1


def _parse_keys(raw: str) -> dict[int, Fernet]:
    keys: dict[int, Fernet] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        version_str, _, key = entry.partition(":")
        if not key:
            raise ImproperlyConfigured(
                "FIELD_ENCRYPTION_KEYS entries must be '<version>:<fernet_key>'."
            )
        keys[int(version_str)] = Fernet(key.encode())
    return keys


def _build() -> tuple[MultiFernet, int]:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEYS_RAW", "") or ""
    active_version = getattr(settings, "FIELD_ENCRYPTION_ACTIVE_KEY_VERSION", 1)

    if not raw:
        if not settings.DEBUG:
            raise ImproperlyConfigured(
                "FIELD_ENCRYPTION_KEYS must be set outside DEBUG (NFR-2)."
            )
        warnings.warn(
            "FIELD_ENCRYPTION_KEYS is not set — generating an ephemeral dev-only key. "
            "Encrypted values will NOT survive a process restart. Set "
            "FIELD_ENCRYPTION_KEYS in .env for anything beyond local scratch use.",
            stacklevel=2,
        )
        return MultiFernet([Fernet(Fernet.generate_key())]), active_version

    keys = _parse_keys(raw)
    if active_version not in keys:
        raise ImproperlyConfigured(
            f"FIELD_ENCRYPTION_ACTIVE_KEY_VERSION={active_version} has no matching "
            "entry in FIELD_ENCRYPTION_KEYS."
        )
    ordered = [keys[active_version]] + [
        fernet for version, fernet in keys.items() if version != active_version
    ]
    return MultiFernet(ordered), active_version


def _get_multi_fernet() -> MultiFernet:
    global _multi_fernet, _active_key_version
    if _multi_fernet is None:
        _multi_fernet, _active_key_version = _build()
    return _multi_fernet


def get_active_key_version() -> int:
    _get_multi_fernet()
    return _active_key_version


def encrypt_value(plaintext: str) -> bytes:
    return _get_multi_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_value(ciphertext: bytes) -> str:
    return _get_multi_fernet().decrypt(bytes(ciphertext)).decode("utf-8")
