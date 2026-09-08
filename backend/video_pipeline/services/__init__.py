"""Pipeline stage services.

Celery tasks in `video_pipeline.tasks` stay thin: they own retries, the
append-only `VideoJobStep` trail and job status transitions. Everything else —
provider HTTP, prompt construction, response parsing, cost accounting — lives
here so it is unit-testable without a broker and without a network.

Implemented today: stage 1 (script) and stage 2 (script moderation).
Stages 3-8 (voice / visuals / assembly / final moderation / upload) are still
stubs in `tasks.py`.
"""
