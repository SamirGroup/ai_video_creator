"""Explicit, expiring per-account exemption for supervised deployment testing."""
import os
from datetime import datetime, timezone


def _exempt_ids() -> set[str]:
    """Ids listed in TEMP_2FA_BYPASS_USER_ID, comma separated.

    Testing needs more than one staff account — a superadmin and whoever is
    checking alongside them — and rotating a single id hands the exemption from
    one to the other instead of covering both.
    """
    raw = os.environ.get("TEMP_2FA_BYPASS_USER_ID", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def temporary_2fa_exemption(user):
    if not user or not user.is_authenticated or not user.is_superuser:
        return False
    if str(user.pk) not in _exempt_ids():
        return False
    try:
        deadline = datetime.fromisoformat(os.environ.get("TEMP_2FA_BYPASS_UNTIL", ""))
        return deadline.tzinfo is not None and datetime.now(timezone.utc) < deadline
    except ValueError:
        return False
