"""Celery app entrypoint, importable as `config.celery:app` (see backend/Dockerfile
and docker-compose.yml celery_worker/celery_beat commands: `celery -A config ...`).
"""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("ai_youtuber")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
