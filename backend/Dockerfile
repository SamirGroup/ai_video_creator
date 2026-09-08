# syntax=docker/dockerfile:1
#
# Multi-stage Dockerfile for the Django + DRF + Celery backend.
# Two runtime targets:
#   dev  -> used by ../docker-compose.yml (bind-mounted source, Django dev server)
#   prod -> used by ../docker-compose.prod.yml (immutable image, gunicorn, non-root)
#
# Assumes the standard layout this project uses:
#   backend/manage.py
#   backend/requirements.txt          (runtime deps: django, djangorestframework, celery, psycopg[binary], ...)
#   backend/requirements-dev.txt      (dev/test extras: pytest, ruff, ... - optional, dev target only)
#   backend/config/                   (Django project package, celery app importable as `config.celery:app`)

########################################
# base — shared OS packages, no secrets
########################################
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Runtime OS deps:
#   libpq5  -> psycopg (PostgreSQL client library)
#   ffmpeg  -> assembly stage (SPEC 7.1 #5) if render worker shares this image
#   curl    -> HEALTHCHECK / readiness probes
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libpq5 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 app && useradd -u 1000 -g app -m -s /usr/sbin/nologin app

########################################
# builder — compiles wheels, kept out of final images
########################################
FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# Dev/test extras are optional — build an empty wheelhouse fallback if the file is missing
# so `dev` target build doesn't hard-fail on repos that haven't added it yet.
COPY requirements-dev.txt ./requirements-dev.txt
RUN pip wheel --wheel-dir /wheels -r requirements-dev.txt

########################################
# dev — local development (docker-compose.yml), hot reload via bind mount
########################################
FROM base AS dev

COPY --from=builder /wheels /wheels
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-index --find-links=/wheels -r requirements.txt -r requirements-dev.txt \
    && rm -rf /wheels

# Source is bind-mounted over this in docker-compose.yml; copied here too so
# `docker build` alone still produces a runnable image (e.g. for CI).
COPY . .
RUN chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/ || exit 1

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

########################################
# prod — small, immutable, non-root, gunicorn
########################################
FROM base AS prod

COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --no-index --find-links=/wheels -r requirements.txt gunicorn \
    && rm -rf /wheels

COPY . .
RUN chown -R app:app /app
USER app

ENV DJANGO_SETTINGS_MODULE=config.settings

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/ || exit 1

CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
