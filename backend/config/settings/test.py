"""Settings for pytest (see pytest.ini). Same DB engine as prod (PostgreSQL:
ArrayField/JSONB), but Celery runs tasks inline, storage is a per-run temp
dir, throttle/cache is in-process, email goes to the in-memory outbox and no
provider is ever called: tests mock the client modules (NFR-38).
"""
from __future__ import annotations

import tempfile

from config.settings.base import *  # noqa: F401,F403

DEBUG = True
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"}
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
AWS_STORAGE_BUCKET_NAME = ""
LOCAL_MEDIA_ROOT = tempfile.mkdtemp(prefix="ai_youtuber_media_")
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# Deterministic encryption key so EncryptedTextField round-trips across the run.
FIELD_ENCRYPTION_KEYS_RAW = FIELD_ENCRYPTION_KEYS_RAW or "1:6ZLV94YeTJcz7iLQpRJpikIY1HgDhJcAged91ywtIMQ="  # noqa: F405
FIELD_ENCRYPTION_ACTIVE_KEY_VERSION = 1
STRIPE_SECRET_KEY = STRIPE_SECRET_KEY or "sk_test_dummy"  # noqa: F405
STRIPE_WEBHOOK_SECRET = STRIPE_WEBHOOK_SECRET or "whsec_dummy"  # noqa: F405
