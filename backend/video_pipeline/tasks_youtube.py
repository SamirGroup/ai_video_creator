"""Celery Beat tasks for post-publish YouTube checks (SPEC 7.1 #9, FR-59, FR-60).

Kept apart from `video_pipeline.tasks` (stage tasks) so Track B and Track C
never edit the same module. Schedules are seeded by
`channels/migrations/0003_beat_schedules.py` (ARCHITECTURE D-7):

* `video_pipeline.check_recent_uploads`  — every 30 minutes
* `video_pipeline.sync_published_videos` — daily

Both are idempotent read-only sweeps against the official Data API; they
consume 1 quota unit per 50 videos.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("video_pipeline.tasks_youtube")


@shared_task(name="video_pipeline.check_recent_uploads", queue="celery", acks_late=True)
def check_recent_uploads() -> dict:
    """FR-59: processing / rejection / copyright status for videos published < 24h ago."""
    from video_pipeline.services.youtube_status import check_recent_uploads as _run

    return _run().as_dict()


@shared_task(name="video_pipeline.sync_published_videos", queue="celery", acks_late=True)
def sync_published_videos() -> dict:
    """FR-60: detect deleted / re-privatised platform videos (revenue exclusion)."""
    from video_pipeline.services.youtube_status import sync_published_videos as _run

    return _run().as_dict()
