"""Resolves `config.settings` to either `dev` or `prod` based on environment.

This exists so both env-var conventions already in the repo work unmodified:
- backend/.env.example -> DJANGO_SETTINGS_MODULE=config.settings.dev (explicit)
- root .env.example / backend/Dockerfile prod stage -> DJANGO_SETTINGS_MODULE=config.settings
  (relies on this module picking dev vs prod at import time)

`manage.py` still defaults to `config.settings.dev` directly, so local
`python manage.py ...` runs are unaffected by this indirection.
"""
from __future__ import annotations

import os


def _is_production() -> bool:
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    if environment in ("production", "prod"):
        return True
    debug_flag = os.environ.get("DEBUG", os.environ.get("DJANGO_DEBUG", "true")).strip().lower()
    return debug_flag in ("false", "0", "no")


if _is_production():
    from config.settings.prod import *  # noqa: F401,F403
else:
    from config.settings.dev import *  # noqa: F401,F403
