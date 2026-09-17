import os
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl
import requests
from django.conf import settings
from rest_framework.exceptions import ValidationError
from .models import TelegramConfig


def config():
    return TelegramConfig.objects.get_or_create(pk=1)[0]


def secret(name):
    return getattr(settings, name, None) or os.environ.get(name, "")


def call(method, payload=None, files=None):
    cfg = config()
    token = secret(cfg.token_secret_ref)
    if not cfg.enabled or not token:
        raise ValidationError("Telegram is not configured.")
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            data=payload or {},
            files=files,
            timeout=120,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise ValueError("Telegram rejected the request")
        return body["result"]
    except (requests.RequestException, ValueError):
        # Requests exceptions can contain the bot token URL: never propagate them.
        raise ValidationError("Telegram request failed.") from None


def validate_init_data(raw, *, now=None):
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValidationError("Invalid Telegram data.")
    pairs = parse_qsl(raw, keep_blank_values=True)
    if len({k for k, v in pairs}) != len(pairs):
        raise ValidationError("Duplicate Telegram fields.")
    data = dict(pairs)
    supplied = data.pop("hash", "")
    cfg = config()
    token = secret(cfg.token_secret_ref)
    if not cfg.enabled or not token:
        raise ValidationError("Telegram is not configured.")
    key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(
        key,
        "\n".join(f"{k}={v}" for k, v in sorted(data.items())).encode(),
        hashlib.sha256,
    ).hexdigest()
    try:
        age = (time.time() if now is None else now) - int(data.get("auth_date", "0"))
        user = json.loads(data.get("user", "{}"))
        if (
            not hmac.compare_digest(expected, supplied)
            or not 0 <= age <= 300
            or not isinstance(user, dict)
            or type(user.get("id")) is not int
            or user["id"] <= 0
        ):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValidationError("Invalid or expired Telegram login.") from None
    return user
