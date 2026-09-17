"""AES-256-GCM writes with authenticated key versions; legacy Fernet reads.

FIELD_ENCRYPTION_KEYS keeps its existing '<version>:<base64-32-byte-key>' format.
Retain old keys until all old rows are rewritten. New writes use a domain-separated
256-bit key; legacy tokens remain readable and upgrade on their next normal save.
"""

from __future__ import annotations

import base64
import os
import struct
import warnings
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

__all__ = ["encrypt_value", "decrypt_value", "InvalidToken", "get_active_key_version"]
_MAGIC = b"AYG1"
_HEADER_SIZE = 8


@lru_cache(maxsize=8)
def _keyring(raw: str, active: int, debug: bool):
    if not 0 < active < 2**32:
        raise ImproperlyConfigured(
            "Encryption key versions must be positive 32-bit integers."
        )
    if not raw:
        if not debug:
            raise ImproperlyConfigured(
                "FIELD_ENCRYPTION_KEYS must be set outside DEBUG."
            )
        warnings.warn(
            "Using an ephemeral development encryption key; set FIELD_ENCRYPTION_KEYS for persistent data.",
            stacklevel=2,
        )
        raw = f"{active}:{Fernet.generate_key().decode()}"
    keys, legacy = {}, {}
    try:
        for entry in raw.split(","):
            version, encoded = entry.strip().split(":", 1)
            version = int(version)
            if version in keys or not 0 < version < 2**32:
                raise ValueError("Invalid or duplicate key version")
            material = base64.b64decode(encoded.encode(), altchars=b"-_", validate=True)
            if len(material) != 32:
                raise ValueError("Keys must contain 32 bytes")
            derived = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=b"ai-youtuber/field-encryption/aes-256-gcm/v1",
            ).derive(material)
            keys[version] = AESGCM(derived)
            legacy[version] = Fernet(encoded.encode())
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(
            "Invalid FIELD_ENCRYPTION_KEYS format or key material."
        ) from exc
    if active not in keys:
        raise ImproperlyConfigured("The active encryption key version is missing.")
    return keys, MultiFernet(
        [legacy[active]] + [v for k, v in legacy.items() if k != active]
    )


def _configured_keys():
    active = getattr(settings, "FIELD_ENCRYPTION_ACTIVE_KEY_VERSION", 1)
    keys, legacy = _keyring(
        getattr(settings, "FIELD_ENCRYPTION_KEYS_RAW", "") or "", active, settings.DEBUG
    )
    return active, keys, legacy


def get_active_key_version() -> int:
    return _configured_keys()[0]


def encrypt_value(plaintext: str) -> bytes:
    version, keys, _ = _configured_keys()
    header = _MAGIC + struct.pack(">I", version)
    nonce = os.urandom(12)
    return (
        header + nonce + keys[version].encrypt(nonce, plaintext.encode("utf-8"), header)
    )


def decrypt_value(ciphertext: bytes) -> str:
    ciphertext = bytes(ciphertext)
    _, keys, legacy = _configured_keys()
    if not ciphertext.startswith(_MAGIC):
        return legacy.decrypt(ciphertext).decode("utf-8")
    if len(ciphertext) < _HEADER_SIZE + 12 + 16:
        raise InvalidToken
    header, nonce, payload = ciphertext[:8], ciphertext[8:20], ciphertext[20:]
    version = struct.unpack(">I", header[4:])[0]
    try:
        return keys[version].decrypt(nonce, payload, header).decode("utf-8")
    except (KeyError, InvalidTag, UnicodeDecodeError) as exc:
        raise InvalidToken from exc
