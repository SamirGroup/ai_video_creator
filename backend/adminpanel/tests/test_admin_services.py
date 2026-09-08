"""FR-79, FR-80, FR-83, FR-84, FR-85 admin panel service layer."""
from __future__ import annotations

import pytest

from accounts.models import Role, UserStatus
from accounts.tests.factories import UserFactory
from adminpanel import services
from audit.models import AuditLog
from content_planning.services import JobNotCancelable
from video_pipeline.models import JobStatus, Stage
from video_pipeline.tests.factories import VideoJobFactory
from video_pipeline.tests.fixtures import llm_config

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff():
    return UserFactory()


@pytest.fixture(autouse=True)
def _stub_stage_tasks(monkeypatch):
    calls: dict[str, list] = {"generate_script": [], "generate_voice": []}

    class _FakeTask:
        def __init__(self, name):
            self.name = name

        def apply_async(self, args=None, **kwargs):
            calls[self.name].append(args)

    import video_pipeline.tasks as tasks_module

    for name in calls:
        monkeypatch.setattr(tasks_module, name, _FakeTask(name))
    return calls


def _audit(resource_type: str, resource_id: str, action: str):
    return AuditLog.objects.filter(resource_type=resource_type, resource_id=resource_id, action=action)


class TestUserModeration:
    def test_suspend_then_reactivate(self, staff):
        user = UserFactory(status=UserStatus.ACTIVE)
        services.suspend_user(staff, user)
        user.refresh_from_db()
        assert user.status == UserStatus.SUSPENDED
        assert not user.is_active  # is_active is derived from status
        assert _audit("user", str(user.id), "admin.user_suspended").exists()

        services.reactivate_user(staff, user)
        user.refresh_from_db()
        assert user.status == UserStatus.ACTIVE
        assert user.is_active

    def test_set_roles_replaces_the_full_set(self, staff):
        user = UserFactory()
        moderator_role, _ = Role.objects.get_or_create(code="moderator", defaults={"name": "Moderator"})
        finance_role, _ = Role.objects.get_or_create(code="finance", defaults={"name": "Finance"})

        services.set_roles(staff, user, [moderator_role.code])
        assert set(user.user_roles.values_list("role__code", flat=True)) == {"moderator"}

        services.set_roles(staff, user, [finance_role.code])
        assert set(user.user_roles.values_list("role__code", flat=True)) == {"finance"}
        assert _audit("user", str(user.id), "admin.roles_changed").count() == 2

    def test_view_user_is_itself_audited(self, staff):
        user = UserFactory()
        services.view_user(staff, user)
        assert _audit("user", str(user.id), "staff.viewed_user").exists()


class TestVideoJobModeration:
    def test_retry_resumes_from_the_current_stage(self, staff, _stub_stage_tasks, django_capture_on_commit_callbacks):
        job = VideoJobFactory(status=JobStatus.FAILED, current_stage=Stage.VOICE, error_code="provider_not_configured")

        with django_capture_on_commit_callbacks(execute=True):
            result = services.retry_job(staff, job)

        assert result.status == JobStatus.QUEUED
        assert result.error_code == ""
        assert _stub_stage_tasks["generate_voice"] == [[str(job.pk)]]
        assert _audit("video_job", str(job.pk), "admin.job_retried").exists()

    def test_retry_rejects_a_non_failed_job(self, staff):
        job = VideoJobFactory(status=JobStatus.QUEUED)
        with pytest.raises(services.JobNotRetryable):
            services.retry_job(staff, job)

    def test_cancel_refunds_quota_when_not_started(self, staff, monkeypatch):
        job = VideoJobFactory(status=JobStatus.QUEUED, started_at=None)
        refund_calls = []
        monkeypatch.setattr(
            "billing.quota.release_quota", lambda user, j: refund_calls.append(j) or object()
        )

        result = services.cancel_job(staff, job)

        assert result.status == JobStatus.CANCELED
        assert refund_calls == [job]
        assert _audit("video_job", str(job.pk), "admin.job_canceled").exists()

    def test_cancel_rejects_a_terminal_job(self, staff):
        job = VideoJobFactory(status=JobStatus.PUBLISHED)
        with pytest.raises(JobNotCancelable):
            services.cancel_job(staff, job)


class TestConfig:
    def test_rotate_secret_accepts_a_resolvable_ref(self, staff, settings):
        # providers/migrations/0002_seed_default_providers.py already seeded a
        # primary "llm" row — this one must not compete for that slot
        # (uq_api_credentials_one_primary_per_service).
        settings.OPENROUTER_API_KEY = "sk-test-value"
        config = llm_config(is_primary=False)
        config.secret_ref = "SOME_OTHER_UNSET_KEY"
        config.save()

        result = services.rotate_secret(staff, config, "OPENROUTER_API_KEY")
        assert result.secret_ref == "OPENROUTER_API_KEY"
        assert _audit("api_credentials_config", str(config.id), "admin.provider_secret_rotated").exists()

    def test_rotate_secret_rejects_an_unresolvable_ref(self, staff):
        config = llm_config(is_primary=False)
        config.save()
        original = config.secret_ref
        with pytest.raises(services.SecretNotResolvable):
            services.rotate_secret(staff, config, "TOTALLY_UNSET_ENV_VAR")
        config.refresh_from_db()
        assert config.secret_ref == original  # rolled back, not left half-changed


class TestSystemHealth:
    def test_queue_depth_counts_only_non_terminal_jobs(self):
        VideoJobFactory(status=JobStatus.GENERATING_SCRIPT)
        VideoJobFactory(status=JobStatus.GENERATING_SCRIPT)
        VideoJobFactory(status=JobStatus.PUBLISHED)

        depth = services.queue_depth_by_status()
        assert depth.get(JobStatus.GENERATING_SCRIPT) == 2
        assert JobStatus.PUBLISHED not in depth

    def test_system_health_shape(self):
        health = services.system_health()
        assert set(health) == {
            "queue_depth_by_status",
            "provider_calls_24h",
            "provider_failures_24h",
            "provider_error_rate_24h",
        }
