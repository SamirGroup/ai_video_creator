"""Custom model fields shared across apps."""
from __future__ import annotations

from django.db import models

from core.crypto import InvalidToken, decrypt_value, encrypt_value


class EncryptedTextField(models.BinaryField):
    """A text field encrypted at rest with Fernet (see core.crypto).

    Stored as BYTEA in PostgreSQL, per SPEC 5 ("Shifrlangan maydonlar: BYTEA,
    nomida `_enc` suffiksi"). Plaintext only ever exists in Python memory —
    never in logs, API responses, or the DB in cleartext (C-5, NFR-2, NFR-3).
    """

    description = "Text encrypted at rest (Fernet / AES-128-CBC+HMAC-SHA256)"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("editable", True)
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value):
        if value is None:
            return None
        return super().get_prep_value(encrypt_value(str(value)))

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        try:
            return decrypt_value(bytes(value))
        except InvalidToken as exc:
            raise ValueError(
                "Unable to decrypt field value — invalid or rotated encryption key."
            ) from exc

    def to_python(self, value):
        if value is None or isinstance(value, str):
            return value
        try:
            return decrypt_value(bytes(value))
        except InvalidToken as exc:
            raise ValueError(
                "Unable to decrypt field value — invalid or rotated encryption key."
            ) from exc

    def value_to_string(self, obj):
        value = self.value_from_object(obj)
        return "" if value is None else value
