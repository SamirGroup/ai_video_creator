"""Structured JSON log formatter (NFR-29). No third-party logging dependency is
added beyond the standard library — this keeps `requirements.txt` untouched while
still giving every log line a consistent, machine-parseable shape with
event/name, level, logger, request id, and duration where available.

Never format secrets: callers must NOT pass tokens/passwords/card data via
`extra=`; this formatter does no redaction of its own.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

_RESERVED_LOG_RECORD_ATTRS = frozenset(logging.LogRecord(
    "", 0, "", 0, "", (), None
).__dict__.keys()) | {"message", "asctime"}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = value

        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# NFR-3: secret masking. Applied to every handler in settings.LOGGING so a
# token/key that slips into `extra=` or a message never reaches stdout/Sentry.
# ---------------------------------------------------------------------------
_SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|cookie|refresh|"
    r"access_key|client_secret|card|cvv|totp)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9\-_.=]+", re.IGNORECASE)
_KEYVAL_RE = re.compile(
    r"((?:token|secret|password|api[_-]?key|client_secret)[\"']?\s*[:=]\s*[\"']?)([^\s\"',}]+)",
    re.IGNORECASE,
)
_MASK = "***"


def mask_value(value):
    """Recursively mask secret-looking keys/values in dicts, lists and strings."""
    if isinstance(value, dict):
        return {
            k: (_MASK if _SENSITIVE_KEY_RE.search(str(k)) else mask_value(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(mask_value(v) for v in value)
    if isinstance(value, str):
        value = _BEARER_RE.sub(r"\g<1>" + _MASK, value)
        value = _KEYVAL_RE.sub(r"\g<1>" + _MASK, value)
    return value


class SecretMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in list(record.__dict__.items()):
            if key in _RESERVED_LOG_RECORD_ATTRS:
                continue
            if _SENSITIVE_KEY_RE.search(key):
                record.__dict__[key] = _MASK
            else:
                record.__dict__[key] = mask_value(value)
        if isinstance(record.msg, str):
            record.msg = mask_value(record.msg)
        if record.args:
            try:
                if isinstance(record.args, tuple):
                    record.args = tuple(mask_value(a) for a in record.args)
                else:
                    record.args = mask_value(record.args)
            except Exception:  # pragma: no cover - never break logging
                pass
        return True
