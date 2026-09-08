"""FR-38..FR-41 approval flow (`video_pipeline.services.approval`).

Every Celery hand-off (`generate_script`/`generate_voice`/`generate_visuals`/
`upload_to_youtube`) is monkeypatched to a recorder — these tests assert the
*decision* (status transition, quota call, audit/notification), never run a
real pipeline stage (NFR-38). `django_capture_on_commit_callbacks` fires the
`transaction.on_commit(...)` hooks the service functions use to enqueue tasks.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from audit.models import AuditLog
from content_planning.models import ApprovalMode
from notifications.models import Notification
from video_pipeline.models import JobStatus, Stage, VideoJob
from video_pipeline.services import approval
from video_pipeline.tests.factories import VideoJobFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stub_stage_tasks(monkeypatch):
    """Replace every Celery task `approval` might enqueue with a call recorder."""
    calls: dict[str, list] = {"generate_script": [], "generate_voice": [], "generate_visuals": [], "upload_to_youtube": []}

    class _FakeTask:
        def __init__(self, name):
            self.name = name

        def apply_async(self, args=None, **kwargs):
            calls[self.name].append(args)

    import video_pipeline.tasks as tasks_module

    for name in calls:
        monkeypatch.setattr(tasks_module, name, _FakeTask(name))
    return calls


@pytest.fixture
def job(db):
    return VideoJobFactory(status=JobStatus.AWAITING_APPROVAL, approval_requested_at=timezone.now())


@pytest.fixture
def user(job):
    return job.user


def _audit(job: VideoJob, action: str):
    return AuditLog.objects.filter(resource_type="video_job", resource_id=str(job.pk), action=action)


# ---------------------------------------------------------------------------
# on_final_moderation_passed (system-triggered, FR-38, FR-40)
# ---------------------------------------------------------------------------
class TestOnFinalModerationPassed:
    def test_review_required_goes_to_awaiting_approval_with_a_preview_token(
        self, django_capture_on_commit_callbacks, _stub_stage_tasks
    ):
        job = VideoJobFactory(status=JobStatus.MODERATING_FINAL)
        job.preference.approval_mode = ApprovalMode.REVIEW_REQUIRED
        job.preference.save(update_fields=["approval_mode"])

        with django_capture_on_commit_callbacks(execute=True):
            new_status = approval.on_final_moderation_passed(job)

        assert new_status == JobStatus.AWAITING_APPROVAL
        job.refresh_from_db()
        assert job.status == JobStatus.AWAITING_APPROVAL
        assert job.approval_requested_at is not None
        assert job.preview_token
        assert job.preview_expires_at > timezone.now()
        assert not _stub_stage_tasks["upload_to_youtube"]
        assert Notification.objects.filter(user=job.user, type="video.awaiting_approval").exists()
        assert _audit(job, "video_job.moderation_passed").exists()

    def test_auto_mode_goes_straight_to_upload_queued(self, django_capture_on_commit_callbacks, _stub_stage_tasks):
        job = VideoJobFactory(status=JobStatus.MODERATING_FINAL)
        job.preference.approval_mode = ApprovalMode.AUTO
        job.preference.save(update_fields=["approval_mode"])

        with django_capture_on_commit_callbacks(execute=True):
            new_status = approval.on_final_moderation_passed(job)

        assert new_status == JobStatus.UPLOAD_QUEUED
        job.refresh_from_db()
        assert job.status == JobStatus.UPLOAD_QUEUED
        assert job.approval_requested_at is None
        assert _stub_stage_tasks["upload_to_youtube"] == [[str(job.pk)]]


# ---------------------------------------------------------------------------
# Creator-triggered (FR-39)
# ---------------------------------------------------------------------------
class TestApprove:
    def test_approve_enqueues_upload_and_records_the_actor(
        self, job, user, django_capture_on_commit_callbacks, _stub_stage_tasks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            result = approval.approve_job(user, job)

        assert result.status == JobStatus.APPROVED
        assert result.approval_actor_id == user.id
        assert result.approved_at is not None
        assert _stub_stage_tasks["upload_to_youtube"] == [[str(job.pk)]]
        assert _audit(job, "video_job.approved").exists()

    def test_approve_rejects_the_wrong_status(self, job, user):
        job.status = JobStatus.GENERATING_SCRIPT
        job.save(update_fields=["status"])
        with pytest.raises(approval.JobNotAwaitingApproval):
            approval.approve_job(user, job)


class TestReject:
    def test_reject_is_terminal_and_stores_the_reason(self, job, user):
        result = approval.reject_job(user, job, "Off-brand tone.")
        assert result.status == JobStatus.REJECTED
        assert result.rejection_reason == "Off-brand tone."
        assert result.rejected_at is not None
        assert result.completed_at is not None
        assert _audit(job, "video_job.rejected").exists()


class TestRequestChanges:
    def test_first_two_regenerations_are_free(self, job, user, django_capture_on_commit_callbacks, _stub_stage_tasks, monkeypatch):
        reserve_calls = []
        monkeypatch.setattr(approval, "reserve_quota", lambda *a, **kw: reserve_calls.append(kw))

        with django_capture_on_commit_callbacks(execute=True):
            result = approval.request_changes(user, job, comment="Make it punchier.", restart_stage=Stage.SCRIPT)

        assert result.status == JobStatus.CHANGES_REQUESTED
        assert result.regeneration_count == 1
        assert reserve_calls == []  # A-21: free
        assert _stub_stage_tasks["generate_script"] == [[str(job.pk)]]
        history = result.script_meta["change_requests"]
        assert history[-1]["restart_stage"] == Stage.SCRIPT
        assert history[-1]["comment"] == "Make it punchier."

    def test_third_regeneration_reserves_quota(self, job, user, django_capture_on_commit_callbacks, _stub_stage_tasks, monkeypatch):
        job.regeneration_count = 2
        job.save(update_fields=["regeneration_count"])
        reserve_calls = []
        monkeypatch.setattr(approval, "reserve_quota", lambda u, **kw: reserve_calls.append(kw) or None)

        with django_capture_on_commit_callbacks(execute=True):
            approval.request_changes(user, job, comment="One more pass.", restart_stage=Stage.VOICE)

        assert reserve_calls == [{"kind": "regeneration", "job": job}]
        assert _stub_stage_tasks["generate_voice"] == [[str(job.pk)]]

    def test_unknown_restart_stage_is_rejected(self, job, user):
        with pytest.raises(approval.JobNotEditable):
            approval.request_changes(user, job, comment="x", restart_stage="upload")


class TestUpdateMetadata:
    def test_updates_only_the_provided_fields(self, job, user):
        original_description = job.description
        result = approval.update_metadata(user, job, {"title": "A better title"})
        assert result.title == "A better title"
        assert result.description == original_description
        assert _audit(job, "video_job.metadata_updated").exists()

    def test_allowed_while_changes_requested_too(self, job, user):
        job.status = JobStatus.CHANGES_REQUESTED
        job.save(update_fields=["status"])
        result = approval.update_metadata(user, job, {"tags": ["a", "b"]})
        assert result.tags == ["a", "b"]

    def test_blocked_once_the_job_moved_on(self, job, user):
        job.status = JobStatus.UPLOADING
        job.save(update_fields=["status"])
        with pytest.raises(approval.JobNotAwaitingApproval):
            approval.update_metadata(user, job, {"title": "Too late"})


# ---------------------------------------------------------------------------
# FR-38 timeout sweep (A-3)
# ---------------------------------------------------------------------------
class TestExpireStaleApprovals:
    def test_expires_without_auto_publish(self, django_capture_on_commit_callbacks, _stub_stage_tasks):
        job = VideoJobFactory(
            status=JobStatus.AWAITING_APPROVAL,
            approval_requested_at=timezone.now() - timedelta(hours=49),
        )
        job.preference.auto_publish_on_timeout = False
        job.preference.save(update_fields=["auto_publish_on_timeout"])

        with django_capture_on_commit_callbacks(execute=True):
            summary = approval.expire_stale_approvals()

        assert summary == {"published": 0, "expired": 1}
        job.refresh_from_db()
        assert job.status == JobStatus.EXPIRED
        assert job.completed_at is not None
        assert not _stub_stage_tasks["upload_to_youtube"]
        assert Notification.objects.filter(user=job.user, type="video.expired").exists()
        assert _audit(job, "video_job.expired").exists()

    def test_auto_publishes_on_timeout_when_opted_in(self, django_capture_on_commit_callbacks, _stub_stage_tasks):
        job = VideoJobFactory(
            status=JobStatus.AWAITING_APPROVAL,
            approval_requested_at=timezone.now() - timedelta(hours=49),
        )
        job.preference.auto_publish_on_timeout = True
        job.preference.save(update_fields=["auto_publish_on_timeout"])

        with django_capture_on_commit_callbacks(execute=True):
            summary = approval.expire_stale_approvals()

        assert summary == {"published": 1, "expired": 0}
        job.refresh_from_db()
        assert job.status == JobStatus.UPLOAD_QUEUED
        assert _stub_stage_tasks["upload_to_youtube"] == [[str(job.pk)]]
        assert Notification.objects.filter(user=job.user, type="video.auto_published_on_timeout").exists()

    def test_leaves_fresh_awaiting_approval_jobs_alone(self, job):
        summary = approval.expire_stale_approvals()
        assert summary == {"published": 0, "expired": 0}
        job.refresh_from_db()
        assert job.status == JobStatus.AWAITING_APPROVAL
