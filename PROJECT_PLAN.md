# PROJECT_PLAN — AI YouTube Content Ecosystem

Status date: 2026-09-07. Source of truth for requirements: `SPEC.md` (v1.1). Design: `ARCHITECTURE.md`.

## 0. Decision on the two folders (2026-09-07)

`AI-Video-Creator-Studio-main/` was evaluated against the technical brief and **rejected as a
source of code**: ~1.5k lines, every "AI module" is `asyncio.sleep(2)` + a fake CDN URL, in-memory
wallet/audit, a hard-coded `president/admin123` login, Kafka client with no fallback, and unrelated
scope (karaoke, president/heir panels, "telepathy"). Nothing in it satisfies C-1..C-5, OAuth,
Stripe, moderation, or the pipeline. `ai_youtuber/` is the real implementation and is the only
codebase that continues. The Studio folder is left untouched for reference.

## 1. Skills applied (Rule #0)

Skill library on this machine: `C:\Users\User\.claude\skills` (the `.agents\skills` path from the
global rules does not exist here). Actively used:

| Skill | Used in |
|---|---|
| `oauth-implementation`, `oauth` | channels OAuth PKCE, token rotation, revoke |
| `stripe-integration`, `stripe-payments`, `adding-stripe` | billing SetupIntent, revenue-share invoices, webhooks, dunning |
| `python-background-jobs`, `23-task-queue-celery` | pipeline stage tasks, idempotency, scheduler |
| `django-pro`, `django-rest-api-development`, `12-django-drf-patterns` | views/serializers/services layout |
| `gdpr-data-handling` | consents, data export/deletion, anonymisation |
| `youtube-automation`, `youtube-seo` | YouTube Data API limits, metadata rules (100-char title, 5000-byte description, 500-char tags), quota costs |
| `python-testing`, `python-testing-patterns` | pytest structure, provider mocking |
| `security-audit`, `django-access-review` | quality gate before merge |
| `writing-tests`, `code-review-checklist` | review phase |

## 2. Current state (audit of `ai_youtuber/`, updated 2026-09-08)

Implemented and tested: auth (register/login/refresh/logout/verify/reset/Google sign-in), OAuth
YouTube + AdSense connect/refresh/revoke, channels list/detail/sync, plans, subscription, Stripe
Checkout/Portal/webhooks, revenue-share invoice service, notifications list/read/preferences, audit
log, provider config + cost accounting, 2FA, sessions, consents, data rights, content preferences +
scheduler, quota enforcement, contracts (sign/PDF/gates), manual generate/cancel — **and the full
video generation pipeline end to end**: script -> script moderation -> voice (ElevenLabs) -> visuals
(Runway) -> FFmpeg assembly -> final moderation (Rekognition) -> **approval flow**
(approve/reject/request-changes/metadata/preview, FR-38..41, 48h auto-expiry) -> YouTube upload ->
post-publish check. **Moderation queue/decide** (FR-48/81) routes an approved flagged job back into
whichever gate stopped it (script -> resume at voice; final -> the approval flow). **Revenue-share
statements** (FR-67..70b): monthly period close with a cent-exact 50/50 split (remainder favours the
creator), idempotent per period, auto-invoices via the existing Stripe service or carries forward
below the $10 minimum; creator summary/daily/by-video/statements/PDF/dispute and admin finance
overview/statements/finalize/CSV-export endpoints are live. All of the above has passing pytest
coverage (video_pipeline, moderation, revenue). All SPEC 5 models exist.

Stubbed (HTTP 501) or missing: admin panel (`adminpanel` app — users list/suspend, video job
monitor/retry/cancel, plan config, provider config, contract-version admin, feature flags, system
health; FR-79/80/83/84/85 — moderation's own admin-facing piece, FR-48/81, is done), invoices
list/PDF (billing app), email templates (en/ru/uz) beyond the types already registered, Prometheus
metrics. Frontend: auth pages hit the real API; every other page still reads `src/mocks`.

Environment on this machine: Python 3.14 venv rebuilt; PostgreSQL 5433 / Redis 6380 / FFmpeg via
Scoop (installed by this plan's P0); no Docker.

## 3. Phases

### P0 — Foundation (this session, orchestrator)
- [x] Rebuild venv, install Scoop PostgreSQL/Redis/FFmpeg, init DB, run existing tests.
- [x] `ARCHITECTURE.md`, `PROJECT_PLAN.md`.
- [x] `core/storage.py` (S3 + local fallback) and `notifications/services.py` (`notify()`), used by every later phase.

### P1 — Backend, parallel tracks (disjoint file ownership)
| Track | Status | Files owned | Delivers |
|---|---|---|---|
| A. Planning + quota + contracts | **done** | `content_planning/*`, `contracts/*`, `billing/quota.py`, `billing/migrations/0002*`, `accounts/consents*` | FR-21..FR-24 quota (`usage_counters`), FR-28..FR-32 contracts (+ SetupIntent FR-70a, PDF snapshot), FR-33..FR-37 preferences + Beat scheduler + manual generate/cancel, `/me/consents` |
| B. Pipeline stages 3–6 + approval | **done, tested** | `video_pipeline/services/{tts_client,video_gen_client,assembler,visual_moderation,approval,checkpoints}.py`, `video_pipeline/tasks.py` (stages voice→final moderation), `video_pipeline/views.py`, `video_pipeline/serializers.py`, `video_pipeline/migrations/0002*`, `video_pipeline/tests/test_approval.py` | FR-38..FR-53 — script→voice→visuals→assembly→final-moderation→approval→upload now chains automatically end to end |
| C. YouTube publish + quota + post-publish | **done** | `channels/youtube_api.py`, `channels/quota.py`, `channels/migrations/0002*`, `video_pipeline/services/youtube_upload.py`, `video_pipeline/tasks.py` (upload + post-publish only) | FR-49, FR-54..FR-60 |
| D. Revenue | **done, tested** | `revenue/*` | FR-61..FR-73 (sync was already done; statements/dispute/period-close/admin-finance added this pass), admin finance |
| E. Admin + moderation + identity extras | **done, tested** | `moderation/*`, `adminpanel/*` (new app), `accounts/{twofactor,sessions,data_rights}*`, `accounts/migrations/0002-3*` | FR-9, FR-79..FR-85, FR-86..FR-89, `/me/sessions` all done |

Shared-file protocol: `config/settings/base.py`, `config/api_urls.py`, `requirements.txt` — append
only, one clearly-marked block per track, never reorder. `video_pipeline/tasks.py` is split between
B and C by function; each track only edits its own functions and the chain hand-off line.

### P2 — Frontend (after P1 endpoints exist)
| Track | Files | Delivers |
|---|---|---|
| F1 creator | `src/pages/creator/*`, `src/hooks/*`, `src/api/*` | replace mocks: channel, preferences, videos, approval, revenue, billing, contract, notifications centre, data rights |
| F2 admin | `src/pages/admin/*` | users, jobs, moderation queue, finance, config, health |
| i18n | `src/i18n/locales/*` | 100% key parity en/ru/uz (CI check) |

### P3 — Quality gates
code-reviewer on each track → security-auditor on accounts/channels/billing/revenue → qa-tester
end-to-end (fixture-driven pipeline run with mocked providers) → fix loops.

### P4 — Ops & docs
Prometheus/Grafana/alert rules, runbooks, README refresh, technical-writer docs, CI additions
(pip-audit, gitleaks, i18n parity, `grep` guard against browser-automation packages).

## 4. Definition of done per track
- Every endpoint returns real data (no 501 left in the track's URL group).
- Tests: unit for services + API tests for views; all providers mocked; `pytest` green; `ruff` clean.
- Migrations generated, reversible, and applied.
- Audit log + notification emitted for every SPEC-listed event.
- No secret in logs/responses (assert in tests where relevant).
