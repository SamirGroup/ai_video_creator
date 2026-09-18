"""Explicit, expiring per-account exemption for supervised deployment testing."""
import os
from datetime import datetime, timezone


def temporary_2fa_exemption(user):
    if not user or not user.is_authenticated or not user.is_superuser:
        return False
    if str(user.pk) != os.environ.get("TEMP_2FA_BYPASS_USER_ID", ""):
        return False
    try:
        deadline = datetime.fromisoformat(os.environ.get("TEMP_2FA_BYPASS_UNTIL", ""))
        return deadline.tzinfo is not None and datetime.now(timezone.utc) < deadline
    except ValueError:
        return False
