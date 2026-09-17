from unittest.mock import patch

import pytest

from video_pipeline.models import JobStatus
from video_pipeline.services.approval import update_metadata
from video_pipeline.services.moderation_proof import metadata_digest
from video_pipeline.services.youtube_upload import YouTubeUploadError, upload_job_video
from video_pipeline.tests.factories import VideoJobFactory

pytestmark = pytest.mark.django_db


def test_metadata_change_invalidates_approval_and_queues_moderation(
    django_capture_on_commit_callbacks,
):
    job = VideoJobFactory(
        status=JobStatus.AWAITING_APPROVAL,
        final_video_s3_key="final/video.mp4",
        moderation_approved_sha256="a" * 64,
    )
    job.moderation_metadata_sha256 = metadata_digest(job)
    job.save()
    with patch("video_pipeline.tasks.moderate_content.apply_async") as enqueue:
        with django_capture_on_commit_callbacks(execute=True):
            update_metadata(job.user, job, {"title": "Changed public title"})
    job.refresh_from_db()
    assert job.status == JobStatus.MODERATING_SCRIPT
    assert not job.moderation_approved_sha256
    assert not job.moderation_metadata_sha256
    enqueue.assert_called_once_with(args=[str(job.pk)], kwargs={"scope": "script"})


def test_unreviewed_metadata_cannot_reach_youtube_or_consume_quota():
    job = VideoJobFactory(
        final_video_s3_key="final/video.mp4", moderation_approved_sha256="a" * 64
    )
    job.moderation_metadata_sha256 = metadata_digest(job)
    job.title = "Unreviewed replacement"
    with patch("video_pipeline.services.youtube_upload.reserve_units") as reserve:
        with pytest.raises(YouTubeUploadError):
            upload_job_video(job)
    reserve.assert_not_called()
