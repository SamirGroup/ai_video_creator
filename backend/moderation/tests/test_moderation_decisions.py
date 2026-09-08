"""Moderator decisions on flagged/blocked jobs (FR-48, FR-81)."""
from __future__ import annotations

import pytest

from accounts.tests.factories import UserFactory
from audit.models import AuditLog
from content_planning.models import ApprovalMode
from moderation import services
from moderation.models import ModerationLog, ModerationStage, ModerationVerdict, ReviewDecision
from notifications.models import Notification
from video_pipeline.models import JobStatus
from video_pipeline.tests.factories import VideoJobFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stub_stage_tasks(monkeypatch):
    calls: dict[str, list] = {"generate_voice": [], "upload_to_youtube": []}

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
def moderator():
    return UserFactory()


def _flagged_job(*, stage: str, approval_mode: str = ApprovalMode.REVIEW_REQUIRED):
    job = VideoJobFactory(status=JobStatus.MODERATION_REVIEW)
    job.preference.approval_mode = approval_mode
    job.preference.save(update_fields=["approval_mode"])
    ModerationLog.objects.create(
        job=job,
        stage=stage,
        provider="openai_moderation" if stage == ModerationStage.SCRIPT else "aws_rekognition",
        verdict=ModerationVerdict.FLAG,
        categories={"violence": 0.65},
        threshold_config={},
        raw_response={},
    )
    return job


class TestDecide:
    def test_approving_a_script_stage_flag_resumes_at_voice(
        self, moderator, django_capture_on_commit_callbacks, _stub_stage_tasks
    ):
        job = _flagged_job(stage=ModerationStage.SCRIPT)

        with django_capture_on_commit_callbacks(execute=True):
            result = services.decide(moderator, job, decision="approved", reason="False positive.")

        assert result.status == JobStatus.SCRIPT_READY
        assert _stub_stage_tasks["generate_voice"] == [[str(job.pk)]]
        log = job.moderation_logs.get()
        assert log.review_decision == ReviewDecision.APPROVED
        assert log.review_reason == "False positive."
        assert log.reviewed_by_id == moderator.id
        assert AuditLog.objects.filter(
            resource_type="video_job", resource_id=str(job.pk), action="moderation.decided"
        ).exists()

    def test_approving_a_final_stage_flag_routes_through_approval(
        self, moderator, django_capture_on_commit_callbacks, _stub_stage_tasks
    ):
        job = _flagged_job(stage=ModerationStage.FINAL, approval_mode=ApprovalMode.REVIEW_REQUIRED)

        with django_capture_on_commit_callbacks(execute=True):
            result = services.decide(moderator, job, decision="approved", reason="Reviewed manually, safe.")

        assert result.status == JobStatus.AWAITING_APPROVAL
        assert not _stub_stage_tasks["upload_to_youtube"]

    def test_approving_a_final_stage_flag_in_auto_mode_queues_upload(
        self, moderator, django_capture_on_commit_callbacks, _stub_stage_tasks
    ):
        job = _flagged_job(stage=ModerationStage.FINAL, approval_mode=ApprovalMode.AUTO)

        with django_capture_on_commit_callbacks(execute=True):
            result = services.decide(moderator, job, decision="approved", reason="Reviewed, safe to publish.")

        assert result.status == JobStatus.UPLOAD_QUEUED
        assert _stub_stage_tasks["upload_to_youtube"] == [[str(job.pk)]]

    def test_rejecting_is_terminal_and_notifies_the_creator(self, moderator, _stub_stage_tasks):
        job = _flagged_job(stage=ModerationStage.SCRIPT)

        result = services.decide(moderator, job, decision="rejected", reason="Genuine policy violation.")

        assert result.status == JobStatus.MODERATION_REJECTED
        assert result.rejection_reason == "Genuine policy violation."
        assert not _stub_stage_tasks["generate_voice"]
        assert Notification.objects.filter(user=job.user, type="video.moderation_rejected").exists()

    def test_rejects_jobs_not_in_the_queue(self, moderator):
        job = VideoJobFactory(status=JobStatus.AWAITING_APPROVAL)
        with pytest.raises(services.JobNotInModerationReview):
            services.decide(moderator, job, decision="approved", reason="x")


class TestModerationQueue:
    def test_lists_only_jobs_in_review_and_can_filter_by_stage(self, moderator):
        script_job = _flagged_job(stage=ModerationStage.SCRIPT)
        final_job = _flagged_job(stage=ModerationStage.FINAL)
        VideoJobFactory(status=JobStatus.AWAITING_APPROVAL)  # not in the queue

        all_jobs = {j.id for j in services.moderation_queue()}
        assert all_jobs == {script_job.id, final_job.id}

        script_only = {j.id for j in services.moderation_queue(stage=ModerationStage.SCRIPT)}
        assert script_only == {script_job.id}
