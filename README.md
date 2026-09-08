# AI YouTube Content Ecosystem

SaaS platform where creators connect their YouTube channel via OAuth, set a niche and publishing
schedule, and the system generates full videos with AI (script → voice → visuals → assembly),
uploads them with the creator's approval, and automatically settles a transparent 50/50 ad-revenue
share. Full requirements live in [`SPEC.md`](./SPEC.md); architecture decisions will live in
`ARCHITECTURE.md` once `solution-architect` publishes it.

## Stack

Backend: Django + DRF, Celery (per-stage queues), PostgreSQL, Redis · Frontend: React + Vite ·
Infra: Docker Compose (MVP — single VPS/Cloud VM per SPEC decision A-25; Kubernetes is Faza 2) ·
Observability: Sentry, Prometheus, Grafana (SPEC 8.5).

## Project structure

```
.
├── backend/                    # Django + DRF + Celery app (owned by backend-developer)
│   ├── Dockerfile              # multi-stage: `dev` (compose) / `prod` (gunicorn, non-root)
│   └── .dockerignore
├── frontend/                   # React + Vite app (owned by frontend-developer, incl. its own Dockerfile)
├── deploy/
│   └── deploy.sh                # scripted VPS deploy: migrate -> health check -> swap -> rollback on failure
├── .github/workflows/ci.yml     # backend-ci (lint+test) and frontend-ci (lint+build), run in parallel
├── docker-compose.yml           # local dev stack: db, redis, backend, celery_worker, celery_beat, frontend
├── docker-compose.prod.yml      # production overrides (gunicorn, resource limits, one-off migrate/collectstatic)
├── .env.example                 # placeholder env vars — copy to `.env`, never commit real secrets
├── SPEC.md                      # full functional/non-functional spec (source of truth for "what")
└── ARCHITECTURE.md              # (to be added by solution-architect) — the "how"
```

## Local development

Prerequisites: Docker + Docker Compose v2.

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD, DJANGO_SECRET_KEY, etc.

docker compose up --build
```

This starts:

| Service         | Purpose                                                        | Port(s)          |
|-----------------|-----------------------------------------------------------------|-------------------|
| `db`            | PostgreSQL 16                                                    | 5432              |
| `redis`         | Redis 7 (Celery broker/result backend, cache, throttling)        | 6379              |
| `backend`       | Django + DRF API (dev server, auto-migrate on boot)              | 8000              |
| `celery_worker` | Celery worker listening to all pipeline queues (dev only)        | —                 |
| `celery_beat`   | Celery beat scheduler (django-celery-beat DB scheduler)          | —                 |
| `frontend`      | React app (Vite dev server or nginx-served build)                | 5173 and/or 3000  |
| `minio`         | (optional, commented out) local S3-compatible storage for dev    | 9000/9001         |

Stop everything: `docker compose down` (add `-v` to also drop the `postgres_data`/`redis_data`
volumes, e.g. for a clean-slate reset).

### Celery queues (SPEC 7.1)

The video generation pipeline uses one queue per stage so each can be scaled/rate-limited
independently: `q_script`, `q_voice`, `q_visual`, `q_render`, `q_upload` (+ the default `celery`
queue for misc tasks). In dev, `celery_worker` listens to all of them. In production, run one
worker service per queue — see the comments in `docker-compose.yml` and `docker-compose.prod.yml`.

## AI pipeline — script stage (implemented)

Stage 1 (**script**, SPEC 7.1 #1) and stage 2 (**script moderation**, FR-45) are wired end to end.
Stages 3-8 (voice, visuals, assembly, final moderation, upload) are still stubs — a job stops at
`script_ready` after passing moderation.

### Provider configuration

Which model is called is **a database row, never a constant in the code** (FR-84, SPEC 5.24). The
`providers` app owns two tables:

- `api_credentials_config` — service → provider/model/prices/thresholds. `secret_ref` stores the
  *name* of an env var (e.g. `OPENROUTER_API_KEY`); key material is never written to the DB (C-5).
- `api_usage_logs` — one row per outbound provider call with tokens and USD cost (FR-51), rolled
  up into `video_jobs.total_cost_usd` and capped by `JOB_COST_CEILING_USD` (FR-52).

`providers/migrations/0002_seed_default_providers.py` seeds the Q3-confirmed defaults:
`llm / openrouter / anthropic/claude-sonnet-4.5` and `moderation / openai_moderation /
omni-moderation-latest`, both `is_primary=true`. ElevenLabs and Runway rows are seeded **inactive**
until their stages are built. To swap model or price, edit the row in Django admin → *Providers* —
no redeploy required.

### Setup

```bash
cp backend/.env.example backend/.env
# minimum required for the script stage:
#   OPENROUTER_API_KEY=sk-or-...
#   OPENAI_API_KEY=sk-...            (or OPENAI_MODERATION_API_KEY for a separate key)

docker compose up -d db redis
docker compose run --rm backend python manage.py migrate
```

Trigger a job manually from a shell (`docker compose exec backend python manage.py shell`):

```python
from video_pipeline.tasks import generate_script
generate_script.delay(str(job.id))   # -> generating_script -> script_ready -> moderating_script
```

`generate_script` chains into `moderate_content(scope="script")` automatically. Verdicts map to
status per SPEC 7.2 / FR-48: `pass` → `script_ready`, `flag`/`block` → `moderation_review` (the
human moderator queue — a failed script is never auto-published *and* never auto-rejected).

### Tuning

All knobs live in `backend/.env.example`; per-provider overrides in `api_credentials_config.config`
take precedence over settings. The ones worth knowing:
`MODERATION_BLOCK_THRESHOLD` (default 0.5), `MODERATION_FLAG_THRESHOLD` (0.2),
`SCRIPT_RECENT_TOPICS_LIMIT` (FR-37, default 20), `SCRIPT_TITLE_SIMILARITY_THRESHOLD` (0.9),
`JOB_COST_CEILING_USD` (FR-52).

### Testing

Every provider call is mocked — the test suite never opens a socket (NFR-38):

```bash
cd backend
pytest video_pipeline/tests -q                      # full stage suite (needs Postgres)
pytest video_pipeline/tests -q -m "not django_db"   # pure logic only, no database needed
```

## CI

`.github/workflows/ci.yml` runs two jobs in parallel on every push/PR to `main`/`develop`:

- **backend-ci** — Python 3.12, `ruff check`, `pytest` against real Postgres 16 + Redis 7 service
  containers.
- **frontend-ci** — Node 20, `npm ci`, `npm run lint`, `npm run build`.

Both jobs guard on the relevant project files existing yet (`backend/requirements.txt`,
`frontend/package.json`) and emit a warning instead of failing while those apps are still being
scaffolded in parallel. Secrets (Stripe keys, OAuth credentials, AI provider keys, etc.) belong in
**GitHub Actions repository/environment secrets** — never in this repo.

## Production deploy (single VPS — SPEC A-25)

MVP target is one Docker-Compose-managed VPS/Cloud VM (PostgreSQL can be self-hosted or a managed
instance). Kubernetes is explicitly out of scope until Faza 2.

```bash
# one-time setup on the VPS
git clone <repo> ai_youtuber && cd ai_youtuber
cp .env.example .env   # fill with production secrets, chmod 600 .env

# every deploy
./deploy/deploy.sh main
```

`deploy/deploy.sh`:

1. Pulls the target git ref and tags images with the short git SHA.
2. Runs migrations in a one-off container **before** touching running containers
   (migrations must stay backward-compatible per NFR-39 — old and new code coexist briefly).
3. Recreates `backend` with `--no-deps` (so `db`/`redis` are never restarted) and health-checks
   `GET /api/health/`.
4. If the health check fails, automatically rolls back to the previous image tag; otherwise
   recreates `celery_worker`, `celery_beat`, and `frontend`, and records the new SHA as
   "last known-good" for `./deploy/deploy.sh --rollback`.

Manual equivalent, if you'd rather run it step by step:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Secrets

Never commit `.env`, API keys, or credentials. Use `.env.example` as the template; store real
values in GitHub Actions secrets (CI) and on the VPS in a `.env` file with `chmod 600` (production),
ideally sourced from a secret manager as the platform matures.
