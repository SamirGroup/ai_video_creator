"""Base Django settings shared by dev and prod (SPEC section 5/6/8)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from core.languages import DEFAULT_LANGUAGE, LANGUAGE_CHOICES, LANGUAGE_CODES

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# backend/.env (copied from backend/.env.example) is read first; docker-compose
# also injects the repo-root .env via `env_file:`, which takes precedence as
# real process environment variables always win over a file read here.
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env.str(
    "SECRET_KEY",
    default=env.str("DJANGO_SECRET_KEY", default="unsafe-dev-key-change-me"),
)
DEBUG = env.bool("DEBUG", default=env.bool("DJANGO_DEBUG", default=True))
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"]),
)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

FRONTEND_BASE_URL = env.str("FRONTEND_BASE_URL", default="http://localhost:5173")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    # Local apps
    "core",
    "accounts",
    "channels",
    "billing",
    "contracts",
    "content_planning",
    "video_pipeline",
    "moderation",
    "providers",
    "revenue",
    "notifications",
    "audit",
    "adminpanel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.RequestIDMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Database (SPEC section 5)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://ai_youtuber:ai_youtuber@localhost:5432/ai_youtuber",
    )
}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"].setdefault("CONN_MAX_AGE", 60)

# ---------------------------------------------------------------------------
# Cache / Celery (Redis)
# ---------------------------------------------------------------------------
REDIS_URL = env.str("REDIS_URL", default="redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = env.str("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env.str(
    "CELERY_RESULT_BACKEND", default="redis://localhost:6379/2"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# Tests/one-off scripts can run tasks inline (config.settings.test sets this).
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True
# SPEC 7.1: one queue per pipeline stage so each can scale/rate-limit independently.
CELERY_TASK_ROUTES = {
    "video_pipeline.tasks.generate_script": {"queue": "q_script"},
    "video_pipeline.tasks.generate_voice": {"queue": "q_voice"},
    "video_pipeline.tasks.generate_visuals": {"queue": "q_visual"},
    "video_pipeline.tasks.assemble_video": {"queue": "q_render"},
    "video_pipeline.tasks.upload_to_youtube": {"queue": "q_upload"},
}

# ---------------------------------------------------------------------------
# Password validation (FR-1: minimum 10 characters)
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization (NFR-34: en/ru/uz)
# ---------------------------------------------------------------------------
LANGUAGE_CODE = DEFAULT_LANGUAGE
LANGUAGES = list(LANGUAGE_CHOICES)
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# CORS (NFR-6)
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"]
)
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# DRF / JWT / OpenAPI
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_EXCEPTION_HANDLER": "core.exceptions.rfc7807_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.CursorPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # FR-7
        "anon": "60/min",
        "user": "120/min",
        "register": "3/hour",
        "login": "5/min",
        "password_reset": "3/hour",
        "two_factor": "5/min",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=14)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env.str("JWT_SIGNING_KEY", default=SECRET_KEY),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

REFRESH_COOKIE_SECURE = not DEBUG

SPECTACULAR_SETTINGS = {
    "TITLE": "AI YouTube Content Ecosystem API",
    "DESCRIPTION": "Creator SaaS: OAuth YouTube/AdSense connect, AI video pipeline, "
    "revenue-share billing. See SPEC.md for full functional requirements.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

# ---------------------------------------------------------------------------
# Field-level encryption (NFR-2, C-5) — see core/crypto.py
# ---------------------------------------------------------------------------
FIELD_ENCRYPTION_KEYS_RAW = env.str("FIELD_ENCRYPTION_KEYS", default="")
FIELD_ENCRYPTION_ACTIVE_KEY_VERSION = env.int(
    "FIELD_ENCRYPTION_ACTIVE_KEY_VERSION", default=1
)

# ---------------------------------------------------------------------------
# Stripe / Google OAuth / AI providers / S3 — non-secret plumbing only;
# actual provider wiring happens where each is used (billing/channels/video_pipeline).
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY = env.str("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = env.str("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = env.str("STRIPE_WEBHOOK_SECRET", default="")

GOOGLE_OAUTH_CLIENT_ID = env.str("GOOGLE_OAUTH_CLIENT_ID", default="")
GOOGLE_OAUTH_CLIENT_SECRET = env.str("GOOGLE_OAUTH_CLIENT_SECRET", default="")
GOOGLE_OAUTH_REDIRECT_URI = env.str(
    "GOOGLE_OAUTH_REDIRECT_URI", default="http://localhost:5173/oauth/youtube/callback"
)
GOOGLE_ADSENSE_REDIRECT_URI = env.str(
    "GOOGLE_ADSENSE_REDIRECT_URI",
    default="http://localhost:5173/oauth/adsense/callback",
)

AWS_STORAGE_BUCKET_NAME = env.str("AWS_STORAGE_BUCKET_NAME", default="")
AWS_STORAGE_ACCESS_KEY_ID = env.str("AWS_STORAGE_ACCESS_KEY_ID", default="")
AWS_STORAGE_SECRET_ACCESS_KEY = env.str("AWS_STORAGE_SECRET_ACCESS_KEY", default="")
AWS_S3_REGION_NAME = env.str("AWS_S3_REGION_NAME", default="us-east-1")
AWS_S3_ENDPOINT_URL = env.str("AWS_S3_ENDPOINT_URL", default="") or None
# core.storage: LocalFileStorage is used whenever the bucket name is empty
# (dev/tests); signed local URLs are served from BACKEND_BASE_URL/internal/media/.
LOCAL_MEDIA_ROOT = env.str("LOCAL_MEDIA_ROOT", default=str(BASE_DIR / "media_local"))
BACKEND_BASE_URL = env.str("BACKEND_BASE_URL", default="http://localhost:8000")
SIGNED_URL_TTL_SEC = env.int("SIGNED_URL_TTL_SEC", default=24 * 60 * 60)  # NFR-7
# AWS Rekognition (FR-46 final moderation) — separate key pair from storage.
AWS_REKOGNITION_ACCESS_KEY_ID = env.str("AWS_REKOGNITION_ACCESS_KEY_ID", default="")
AWS_REKOGNITION_SECRET_ACCESS_KEY = env.str(
    "AWS_REKOGNITION_SECRET_ACCESS_KEY", default=""
)
AWS_REKOGNITION_REGION = env.str("AWS_REKOGNITION_REGION", default="us-east-1")
FFMPEG_BINARY = env.str("FFMPEG_BINARY", default="ffmpeg")
FFPROBE_BINARY = env.str("FFPROBE_BINARY", default="ffprobe")

# ---------------------------------------------------------------------------
# AI provider secrets (SPEC 5.24 `api_credentials_config.secret_ref`)
#
# These names are referenced *by name* from api_credentials_config rows — the
# pipeline resolves `secret_ref` -> setting/env at call time and never persists
# or logs the value (C-5, NFR-3, FR-84). Which provider/model is actually used
# is a DB row, not a setting.
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY = env.str("OPENROUTER_API_KEY", default="")
OPENAI_API_KEY = env.str("OPENAI_API_KEY", default="")
# Separate key for the moderation gate so it can be rotated / rate-limited apart
# from any other OpenAI usage; falls back to the shared OPENAI_API_KEY.
OPENAI_MODERATION_API_KEY = (
    env.str("OPENAI_MODERATION_API_KEY", default="") or OPENAI_API_KEY
)
ELEVENLABS_API_KEY = env.str("ELEVENLABS_API_KEY", default="")
RUNWAY_API_KEY = env.str("RUNWAY_API_KEY", default="")

# ---------------------------------------------------------------------------
# Script generation stage (FR-33..FR-37, FR-45, FR-51..FR-53, C-6)
# Every value here is an operational default; per-provider overrides live in
# `api_credentials_config.config` (JSONB) and win over these.
# ---------------------------------------------------------------------------
OPENROUTER_BASE_URL = env.str(
    "OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1/chat/completions"
)
# OpenRouter attribution headers (optional but recommended by the provider).
OPENROUTER_APP_URL = env.str("OPENROUTER_APP_URL", default=FRONTEND_BASE_URL)
OPENROUTER_APP_TITLE = env.str(
    "OPENROUTER_APP_TITLE", default="AI YouTube Content Ecosystem"
)

# SPEC 7.1: the script stage has a 5-minute budget; a single HTTP call gets less
# so a hung request still leaves room for the Celery retry chain.
SCRIPT_LLM_TIMEOUT_SEC = env.int("SCRIPT_LLM_TIMEOUT_SEC", default=120)
SCRIPT_LLM_MAX_OUTPUT_TOKENS = env.int("SCRIPT_LLM_MAX_OUTPUT_TOKENS", default=4000)
SCRIPT_LLM_TEMPERATURE = env.float("SCRIPT_LLM_TEMPERATURE", default=0.8)
# FR-37: how many recent titles are fed back as "do not repeat these" context.
SCRIPT_RECENT_TOPICS_LIMIT = env.int("SCRIPT_RECENT_TOPICS_LIMIT", default=20)
# FR-37: lexical near-duplicate guard on the generated title (0..1).
SCRIPT_TITLE_SIMILARITY_THRESHOLD = env.float(
    "SCRIPT_TITLE_SIMILARITY_THRESHOLD", default=0.9
)
# One extra in-task regeneration when the title collides with a recent one,
# before giving up and letting the Celery retry policy take over.
SCRIPT_MAX_DEDUP_ATTEMPTS = env.int("SCRIPT_MAX_DEDUP_ATTEMPTS", default=2)
# Words per minute used to sanity-check the model's own duration estimate.
SCRIPT_WORDS_PER_MINUTE = env.int("SCRIPT_WORDS_PER_MINUTE", default=150)

# FR-52: hard per-job spend ceiling; the job stops instead of running away.
JOB_COST_CEILING_USD = env.str("JOB_COST_CEILING_USD", default="5.00")

# ---------------------------------------------------------------------------
# Moderation gate (FR-45, FR-48)
# ---------------------------------------------------------------------------
OPENAI_MODERATION_URL = env.str(
    "OPENAI_MODERATION_URL", default="https://api.openai.com/v1/moderations"
)
MODERATION_TIMEOUT_SEC = env.int("MODERATION_TIMEOUT_SEC", default=30)
# Any category score >= block threshold -> verdict=block; >= flag threshold -> flag.
MODERATION_BLOCK_THRESHOLD = env.float("MODERATION_BLOCK_THRESHOLD", default=0.5)
MODERATION_FLAG_THRESHOLD = env.float("MODERATION_FLAG_THRESHOLD", default=0.2)
# FR-48: a blocked script is NEVER auto-rejected — it goes to the human
# moderator queue. Flip only if an operator explicitly wants hard auto-reject.
MODERATION_AUTO_REJECT_ON_BLOCK = env.bool(
    "MODERATION_AUTO_REJECT_ON_BLOCK", default=False
)
MODERATION_MAX_CHARS_PER_CHUNK = env.int("MODERATION_MAX_CHARS_PER_CHUNK", default=8000)

# ---------------------------------------------------------------------------
# Email (FR-2, FR-6, FR-74)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env.str(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env.str("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="no-reply@example.com")

# ---------------------------------------------------------------------------
# Observability (NFR-29)
# ---------------------------------------------------------------------------
SENTRY_DSN = env.str("SENTRY_DSN", default="")
ENVIRONMENT = env.str("ENVIRONMENT", default="development")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "core.logging_utils.JSONFormatter"},
    },
    "filters": {
        "mask_secrets": {"()": "core.logging_utils.SecretMaskingFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["mask_secrets"],
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# --- Track C ---
# YouTube publish / quota budget / post-publish checks (FR-49, FR-54..FR-60, SPEC 5.26, R-4).
# One Google Cloud project = one daily quota bucket. The id is only a counter
# key for `quota_usage`; it is never sent to Google.
GOOGLE_CLOUD_PROJECT_ID = env.str("GOOGLE_CLOUD_PROJECT_ID", default="default")
YOUTUBE_DAILY_QUOTA_UNITS = env.int("YOUTUBE_DAILY_QUOTA_UNITS", default=10_000)
YOUTUBE_DAILY_UPLOAD_LIMIT = env.int("YOUTUBE_DAILY_UPLOAD_LIMIT", default=50)
# Published unit costs: videos.insert = 1600, thumbnails.set = 50, *.list = 1.
YOUTUBE_UPLOAD_COST_UNITS = env.int("YOUTUBE_UPLOAD_COST_UNITS", default=1600)
YOUTUBE_THUMBNAIL_COST_UNITS = env.int("YOUTUBE_THUMBNAIL_COST_UNITS", default=50)
YOUTUBE_LIST_COST_UNITS = env.int("YOUTUBE_LIST_COST_UNITS", default=1)
# FR-58: admins are warned once per quota day at this percentage of either budget.
YOUTUBE_QUOTA_WARN_PERCENT = env.int("YOUTUBE_QUOTA_WARN_PERCENT", default=80)
# Google resets quota at midnight Pacific Time (FR-57).
YOUTUBE_QUOTA_TIMEZONE = env.str(
    "YOUTUBE_QUOTA_TIMEZONE", default="America/Los_Angeles"
)
# FR-54: resumable upload chunking. Must be a multiple of 256 KiB.
YOUTUBE_UPLOAD_CHUNK_SIZE_BYTES = env.int(
    "YOUTUBE_UPLOAD_CHUNK_SIZE_BYTES", default=8 * 1024 * 1024
)
YOUTUBE_UPLOAD_MAX_CHUNK_RETRIES = env.int(
    "YOUTUBE_UPLOAD_MAX_CHUNK_RETRIES", default=5
)
# FR-59: how long after publish the processing/rejection status is polled.
YOUTUBE_POST_PUBLISH_WINDOW_HOURS = env.int(
    "YOUTUBE_POST_PUBLISH_WINDOW_HOURS", default=24
)
CELERY_TASK_ROUTES.update(
    {
        "video_pipeline.check_recent_uploads": {"queue": "celery"},
        "video_pipeline.sync_published_videos": {"queue": "celery"},
    }
)

# ---------------------------------------------------------------------------
# --- Track A --- content planning, scheduler, quota (FR-23, FR-33..FR-36)
# ---------------------------------------------------------------------------
# FR-33: fixed niche list the creator picks from (plus a free-text brief).
CONTENT_NICHES = [
    "travel",
    "cooking",
    "motivation",
    "technology",
    "finance",
    "health",
    "education",
    "science",
    "history",
    "gaming",
    "lifestyle",
    "business",
    "productivity",
    "entertainment",
    "sports",
    "nature",
    "diy",
    "parenting",
]
SUPPORTED_CONTENT_LANGUAGES = list(LANGUAGE_CODES)
VIDEO_DURATION_MIN_SEC = 30
VIDEO_DURATION_MAX_SEC = 600
# FR-35: create `scheduled` jobs this far ahead of the publish slot.
SCHEDULER_LEAD_TIME_HOURS = env.int("SCHEDULER_LEAD_TIME_HOURS", default=24)
# Generation starts `scheduled_for - this` so the video is ready for approval on time.
PIPELINE_EXPECTED_DURATION_MINUTES = env.int(
    "PIPELINE_EXPECTED_DURATION_MINUTES", default=90
)
# A `scheduled` job whose slot is older than this (held by a gate the whole time) is canceled.
SCHEDULER_STALE_AFTER_HOURS = env.int("SCHEDULER_STALE_AFTER_HOURS", default=48)
# "Sign your contract"/"quota exhausted" scheduler notifications: at most one per day per reason.
SCHEDULER_NOTIFY_DEDUPE_SEC = env.int(
    "SCHEDULER_NOTIFY_DEDUPE_SEC", default=24 * 60 * 60
)

AUTO_MODERATION_REVISIONS = env.bool("AUTO_MODERATION_REVISIONS", default=True)
MAX_MODERATION_REVISIONS = env.int("MAX_MODERATION_REVISIONS", default=3)
MODERATION_REVISION_BUDGET_USD = env.str(
    "MODERATION_REVISION_BUDGET_USD", default="30.00"
)

INSTALLED_APPS += ["telegram_integration"]
TELEGRAM_WEBHOOK_BASE_URL = env.str("TELEGRAM_WEBHOOK_BASE_URL", default="")
