# ARCHITECTURE — AI YouTube Content Ecosystem

> Answers **HOW** the system described in [`SPEC.md`](./SPEC.md) is built. SPEC wins on any conflict
> about *what* is built; this document wins on *how*. Version 1.0 · 2026-09-07.

## 0. Hard constraints carried into every design decision

| ID | Constraint | Architectural consequence |
|---|---|---|
| C-1 / C-2 | Never create/activate Google accounts; OAuth 2.0 (code + PKCE) only; no browser automation | The only Google touchpoints are `google-auth-oauthlib` (consent) and `google-api-python-client` (official APIs). No Selenium/Playwright dependency is allowed in `requirements.txt`. CI greps for them. |
| C-4 | Django + DRF backend, React frontend | `backend/` is one Django project with one app per bounded context; `frontend/` is Vite + React 19 + TS. |
| C-5 / NFR-2 | Tokens never plain-text, never logged, never returned | `core.fields.EncryptedTextField` (Fernet/MultiFernet, key versions in env). Serializers never expose `*_enc` fields. JSON log formatter masks `token|secret|key|authorization`. |
| Q1 | Service-fee revenue model | Money flows creator→platform via Stripe Billing invoices. Stripe Connect tables exist but are dormant (F2). |
| Q3 | Runway + ElevenLabs + English-only content | Provider rows in `api_credentials_config`; language validation allows `en` only in MVP. |

## 1. Deployment topology (MVP, A-25)

```
                     ┌──────────────────────────── single VPS / Cloud VM ───────────────────────────┐
 Browser ── HTTPS ──▶│ nginx (TLS, static frontend/dist, /api → gunicorn)                             │
                     │   ├─ backend (gunicorn, Django+DRF, stateless, N replicas)                     │
                     │   ├─ celery_worker  -Q q_script,q_voice,q_visual,q_upload,celery  (I/O bound)  │
                     │   ├─ celery_render  -Q q_render   (FFmpeg, CPU bound, own pool, concurrency=1) │
                     │   ├─ celery_beat    (django-celery-beat DatabaseScheduler)                     │
                     │   ├─ redis (broker db1, results db2, cache/throttle/OAuth-state db0)           │
                     │   └─ postgres 16 (managed instance in prod; PITR)                              │
                     └──────────────────────────────────────────────────────────────────────────────┘
 External: S3 (private bucket, signed URLs) · Stripe · Google OAuth/YouTube/Analytics/AdSense ·
           OpenRouter · ElevenLabs · Runway · OpenAI Moderation · AWS Rekognition · SendGrid · Sentry
```

Local dev without Docker: `start-local.ps1` (Scoop PostgreSQL :5433, Redis :6380, FFmpeg on PATH).
Docker: `docker-compose.yml` (dev) + `docker-compose.prod.yml` (gunicorn, resource limits).

## 2. Backend module map (Django apps = bounded contexts)

| App | Owns (tables) | Key services | Depends on |
|---|---|---|---|
| `core` | — | `crypto`, `fields.EncryptedTextField`, `models.TimestampedModel/AppendOnlyModel`, RFC 7807 handler, RequestID middleware, RBAC permissions, `storage` (S3 signed URLs) | — |
| `accounts` | users, roles, user_roles, (consents, sessions) | register/login/JWT (httpOnly refresh cookie, rotation + blacklist), email verify, password reset, Google sign-in, TOTP 2FA (staff), data rights | core, audit, notifications |
| `channels` | youtube_channels, adsense_accounts | OAuth PKCE flows (YouTube, AdSense), token refresh/revoke, channel sync, YouTube Data API client factory, quota accounting (`quota_usage`) | core, audit |
| `billing` | plans, subscriptions, usage_counters, webhook_events | Stripe Checkout/Portal/SetupIntent, webhook dispatch, quota reserve/release, dunning | audit, revenue (invoices) |
| `contracts` | contract_versions, contracts | current version, sign (hash + PDF snapshot to S3), history, re-consent gate | core.storage, billing (FR-70a), audit |
| `content_planning` | content_preferences | preferences CRUD, pause/resume, Beat scheduler that materialises `scheduled` jobs, manual "generate now" | billing (quota), contracts (gate), video_pipeline |
| `video_pipeline` | video_jobs, video_job_steps, video_assets, music_tracks | stage tasks (script, voice, visuals, assembly, moderation, upload, post-publish), approval flow, preview URLs, cost ceiling | providers, moderation, channels, notifications |
| `moderation` | moderation_logs | script + final gates, moderator queue/decide | video_pipeline |
| `providers` | api_credentials_config, api_usage_logs | provider selection, secret resolution, cost accounting, admin config | — |
| `revenue` | revenue_records, revenue_share_statements, invoices, ledger_entries, stripe_connected_accounts, payouts | Analytics/AdSense sync, period close, statements, disputes, revenue-share invoices, finance reports/export | channels, billing, contracts |
| `notifications` | notifications, notification_preferences | `notify(user, type, ctx)` fan-out to in-app + email (en/ru/uz templates) | — |
| `audit` | audit_logs | `record_audit_event` | — |
| `adminpanel` (new) | — | staff endpoints: users, jobs, queues, health, plans, providers, contract versions, feature flags | all |

Rule: **views are thin; every side-effect lives in `<app>/services.py` (or `services/` package) and is unit-tested by mocking the module boundary.** Cross-app calls go through service functions, never through views or direct model writes from another app.

## 3. Request path and cross-cutting concerns

* URL base `/api/v1/` (`config/api_urls.py` includes each app's `urls.py`). OpenAPI via drf-spectacular at `/api/schema`.
* Auth: `Authorization: Bearer <access>` (15 min). Refresh in httpOnly cookie (`accounts/cookies.py`), rotated + blacklisted (simplejwt blacklist app).
* Errors: `core.exceptions.rfc7807_exception_handler` → `application/problem+json` with `request_id`.
* Pagination: cursor (`PAGE_SIZE=20`). Filtering: django-filter.
* Throttling: DRF scoped throttles (FR-7); counters in Redis cache; cleared per test (`conftest.py`).
* Idempotency: financial mutating endpoints require `Idempotency-Key`; stored in cache 24h keyed by `(user, key)` → response replay.
* RBAC: `core.permissions.HasRole` subclasses. Staff endpoints additionally require `user.is_totp_enabled` once 2FA ships (FR-9) — enforced by `IsStaffWith2FA` permission.
* Logging: JSON (`core.logging_utils.JSONFormatter`) with `request_id`/`job_id`; secret-masking filter (NFR-3) applied to every handler.

## 4. Video pipeline (SPEC 7)

### 4.1 Queues and workers

| Queue | Tasks | Worker profile |
|---|---|---|
| `q_script` | `generate_script` | I/O, concurrency 4 |
| `celery` | `moderate_content`, scheduler, sync, notifications, post-publish checks | I/O, concurrency 8 |
| `q_voice` | `generate_voice` | I/O, concurrency 4 |
| `q_visual` | `generate_visuals` | I/O + long polling, concurrency 4, rate-limited per provider |
| `q_render` | `assemble_video` | CPU (FFmpeg), concurrency 1–2, separate container |
| `q_upload` | `upload_to_youtube` | I/O, concurrency 2, quota-gated |

### 4.2 Stage contract (every task)

1. Load job; skip if terminal (`is_terminal()`), skip if `status` is not the expected predecessor (idempotent re-delivery).
2. `VideoJobStep(status=started, attempt=n)` row **before** any provider call; result row appended after (append-only).
3. Provider call through `providers.services.get_primary_config(service)` + `resolve_api_key`; every call writes `api_usage_logs`; `job.total_cost_usd` recomputed; `CostCeilingExceeded` → `failed(cost_ceiling)` + admin alert (FR-52).
4. Output artifact uploaded to S3 (`core.storage.put_bytes/put_file`) and recorded in `video_assets` (checkpoint, FR-43). On retry, if the asset for `(job, kind)` already exists and its checksum matches, the stage is skipped (`StepStatus.SKIPPED`).
5. `ProviderRetryableError` → `retrying` + FR-44 ladder (30s/2m/8m ± jitter); other `ProviderError` → `failed`; on `failed`: quota refunded (`billing.services.release_quota`), creator notified, admin alert.
6. On success: status advanced, next stage enqueued with `apply_async(queue=...)`.

### 4.3 Stage specifics

| Stage | Provider adapter | Notes |
|---|---|---|
| script | `services/llm_client.OpenRouterClient` | done; produces segments with `visual_prompt` + `target_duration_sec` |
| script moderation | `services/script_moderation` | done; flag/block → `moderation_review` |
| voice | `services/tts_client.ElevenLabsClient` | per-segment TTS → concatenated MP3 + `segment_timing` JSON in asset metadata; cost per char |
| visuals | `services/video_gen_client.RunwayClient` | per-segment text→video (or image→video) jobs, async polling with backoff; clip length = segment duration (loop/trim in assembly); cost per second |
| assembly | `services/assembler.FFmpegAssembler` | downloads clips/voice/music to a temp dir, builds concat list, `-filter_complex` for ducking (`sidechaincompress`) + fades, intro/outro cards from templates, 1080p H.264/AAC, thumbnail = frame at 20% + title overlay. Output MP4 + thumbnail → S3 |
| final moderation | `services/visual_moderation.RekognitionModerator` | keyframes every N seconds via FFmpeg → `DetectModerationLabels`; audio transcript reuses script text |
| review | `services/approval` | sets `awaiting_approval`, preview signed URL (24h), notification; Beat task expires after 48h (FR-38) |
| upload | `services/youtube_upload` | `MediaFileUpload(resumable=True, chunksize=8MB)`, `videos.insert` with `status.selfDeclaredMadeForKids`, `status.containsSyntheticMedia=true` (FR-49), then `thumbnails.set`; quota accounting before call; `quotaExceeded` → re-schedule at next PT midnight (job stays `upload_queued`); `invalid_grant`/`forbidden` → channel disconnected |
| post-publish | `services/youtube_status` | Beat task every 30 min for 24h: `videos.list(part=status,processingDetails)` → `youtube_upload_status`, `youtube_rejected`, `deleted_on_youtube` |

Music (FR-47): `music_tracks` licensed library; selection by `preference.music_style`/mood; attribution appended to description when required.

### 4.4 Scheduler (FR-35/36)

`content_planning.tasks.materialise_scheduled_jobs` (Beat, every 15 min): for each active, unpaused preference with a signed contract, active subscription and connected channel, compute next publish datetime in `publish_timezone`; if within lead time (24h) and no job exists for that slot, `reserve_quota` and create `VideoJob(status=scheduled, scheduled_for=...)`. `enqueue_due_jobs` (every 5 min): `scheduled` jobs whose generation must start now (scheduled_for − expected pipeline duration) → `queued` → `generate_script.apply_async`.

## 5. Revenue and money (SPEC 4.10–4.11, Q1)

* **Daily sync** (`revenue.tasks.sync_channel_revenue`, Beat 04:00 UTC, fan-out per channel): YouTube Analytics `reports.query` for the last 35 days (FR-63) at video granularity (`dimensions=day,video`, `filters=video==<platform ids>`) and channel level; upsert on `(source, channel, youtube_video_id, date)`. Rows older than 72h get `is_final=true`. AdSense (`accounts.reports.generate`) when connected → `source=adsense` rows shown as "AdSense-confirmed".
* **Period close** (Beat on the 10th, A-9): per creator, sum `estimated_revenue` of `is_platform_generated` jobs' videos with `is_final=true` → statement (50/50, cents, ROUND_HALF_UP, remainder to creator side so `platform + creator == gross`), status `draft` → finance finalises → `create_revenue_share_invoice` (Stripe Invoice on the saved payment method, ≥ $10 else `carried_forward`) → ledger entries (debit creator receivable / credit platform revenue) → dunning via Stripe webhooks (FR-70b pauses generation after grace period).
* Every financial transition: `audit_logs` + `ledger_entries` (append-only, `AppendOnlyModel`).

## 6. Storage

`core/storage.py` wraps boto3 (`AWS_S3_ENDPOINT_URL` allows MinIO in dev; `LocalFileStorage` fallback when bucket unset so tests and local runs need no S3). Key layout: `jobs/<job_id>/<kind>/<seq>.<ext>`, `contracts/<user_id>/<contract_id>.pdf`, `statements/<user_id>/<statement_id>.pdf`, `exports/<user_id>/<request_id>.zip`. Signed GET URLs default 24h (NFR-7). Lifecycle: raw assets 30 days, final videos 12 months (A-18) — configured on the bucket, mirrored by a weekly cleanup task.

## 7. Frontend

Vite + React 19 + TS, TanStack Query (server state), Zustand (auth/ui), react-hook-form + zod, i18next (en/ru/uz), Tailwind 4. `src/api/*` are the only modules that touch axios; hooks in `src/hooks/*` wrap them; pages never call axios directly. Mocks in `src/mocks/` are removed page by page as endpoints go live. Role-guarded admin routes are UX only — the server is the authority.

## 8. Security controls checklist (NFR-1..NFR-10)

HSTS + secure cookies (prod settings) · Fernet field encryption with key rotation · secret-masking log filter · PKCE + one-time state (10 min) + exact redirect URI · Stripe signature verification, 400 on failure, event stored · DRF throttles · CSP/X-Frame-Options/nosniff headers via middleware · signed URLs only, private bucket · staff 2FA + audit on every staff read of user data · pip-audit + gitleaks in CI · `security-auditor` gate before auth/billing merges.

## 9. Observability

JSON logs with correlation ids · Sentry (backend+frontend, `send_default_pii=False`) · Prometheus via `django-prometheus` + Celery exporter: `stage_duration_seconds`, `stage_failures_total`, `queue_depth`, `job_cost_usd`, `youtube_quota_units_used` · Grafana dashboards + NFR-32 alert rules in `deploy/monitoring/` · `/health/live`, `/health/ready` (DB + Redis + broker).

## 10. Testing strategy (NFR-37/38)

pytest-django + factory_boy; every external provider mocked with `responses`/`unittest.mock` at the client-module boundary; Celery `task_always_eager=False` — tasks are called directly in tests; FFmpeg tests skipped unless `ffmpeg` on PATH (CI installs it); coverage gates 80% overall, 90% for billing/revenue/moderation/channels. Frontend: vitest + Testing Library for hooks/pages against MSW-style fetch mocks.

## 11. Decisions log (ADR-style, short)

| # | Decision | Why |
|---|---|---|
| D-1 | Fernet (AES-128-CBC+HMAC) instead of raw AES-256-GCM | Authenticated, key-versioned, battle-tested in `cryptography`; satisfies "encrypted at rest, rotatable"; can be swapped behind `core.crypto` without touching callers |
| D-2 | One Django project, many apps (modular monolith) | 500 creators/200 videos-day fits one deployable; microservices would multiply OAuth/secret surfaces |
| D-3 | Provider config in DB (`api_credentials_config`), secrets by reference | FR-84; rotate without deploy; no model names in code |
| D-4 | Celery stage-per-queue, idempotency key `(job, stage, attempt)`, S3 checkpoints | FR-42/43/44/NFR-25 |
| D-5 | Service-fee invoices via Stripe Billing, Connect dormant | Q1 decision; AdSense ToS risk R-1 |
| D-6 | Local file storage fallback when S3 unset | tests and single-machine dev run without cloud credentials |
| D-7 | Beat schedules stored in DB (`django-celery-beat`) but seeded by a data migration | ops can tune intervals; fresh installs still get the schedule |
