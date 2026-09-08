"""End-to-end script stage against the database, with every provider mocked
(NFR-38: CI never calls a real API).

Covers: persistence, FR-43 checkpoint/idempotency, FR-37 de-duplication,
FR-51 cost logging, FR-52 ceiling, FR-45/FR-48 moderation verdict -> job status,
and the append-only `video_job_steps` trail.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from moderation.models import ModerationLog, ModerationStage, ModerationVerdict
from providers.exceptions import ProviderNotConfigured, ProviderRateLimitError
from providers.models import ApiCredentialConfig, ApiUsageLog, ServiceType
from providers.services import get_primary_config
from video_pipeline.models import (
    AssetKind,
    JobStatus,
    Stage,
    StepStatus,
    VideoAsset,
    VideoJobStep,
)
from video_pipeline.services.exceptions import CostCeilingExceeded, JobNotReady
from video_pipeline.services.llm_client import LLMResponse
from video_pipeline.services.script_generation import (
    collect_recent_topics,
    generate_script_for_job,
)
from video_pipeline.services.script_moderation import (
    apply_verdict_to_job,
    moderate_script_for_job,
)
from video_pipeline.tests.factories import VideoJobFactory
from video_pipeline.tests.fixtures import VALID_SCRIPT_PAYLOAD, moderation_payload

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
class StubLLMClient:
    """Returns queued `LLMResponse` objects (or raises queued exceptions)."""

    def __init__(self, items):
        self.items = list(items)
        self.calls: list[list[dict]] = []

    def chat_completion(self, *, messages, **kwargs):
        self.calls.append(messages)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def llm_response(payload=None, *, prompt_tokens=1200, completion_tokens=800, cost=None):
    return LLMResponse(
        content=json.dumps(payload if payload is not None else VALID_SCRIPT_PAYLOAD),
        model="anthropic/claude-sonnet-4.5",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        provider_cost_usd=Decimal(str(cost)) if cost is not None else None,
        request_id="gen-integration-1",
        latency_ms=1234,
        http_status=200,
        finish_reason="stop",
    )


class StubModerationClient:
    def __init__(self, items):
        self.items = list(items)
        self.calls: list[list[str]] = []

    def moderate(self, chunks):
        self.calls.append(chunks)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item, 120, 200


@pytest.fixture
def job():
    return VideoJobFactory()


# ---------------------------------------------------------------------------
# The seed data migration (SPEC 5.24)
# ---------------------------------------------------------------------------
class TestSeededProviderConfiguration:
    def test_primary_llm_row_is_openrouter_claude(self):
        config = get_primary_config(ServiceType.LLM)
        assert config.provider == "openrouter"
        assert config.model_name == "anthropic/claude-sonnet-4.5"
        assert config.secret_ref == "OPENROUTER_API_KEY"

    def test_primary_moderation_row_is_openai(self):
        config = get_primary_config(ServiceType.MODERATION)
        assert config.provider == "openai_moderation"
        assert config.secret_ref == "OPENAI_MODERATION_API_KEY"

    def test_not_yet_implemented_stages_have_no_primary_provider(self):
        # Placeholder rows exist for the admin UI but must not be selectable,
        # otherwise a half-built stage would look configured.
        for service in (ServiceType.TTS, ServiceType.VIDEO_GEN):
            with pytest.raises(ProviderNotConfigured):
                get_primary_config(service)

    def test_no_api_key_material_is_stored_in_the_database(self):
        for config in ApiCredentialConfig.objects.all():
            serialized = json.dumps(config.config)
            assert "sk-" not in serialized
            assert "api_key" not in serialized.lower()


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------
class TestGenerateScript:
    def test_persists_metadata_script_and_duration(self, job):
        client = StubLLMClient([llm_response()])
        script = generate_script_for_job(job, client=client)

        job.refresh_from_db()
        assert job.title == VALID_SCRIPT_PAYLOAD["title"]
        assert job.description.startswith("Sagardotegi cider")
        assert job.tags == ["basque cider", "sagardotegi", "txotx", "food travel", "cider"]
        assert len(job.script_text.split("\n\n")) == 3
        assert job.duration_sec == script.estimated_duration_sec > 0
        assert job.language == "en"

    def test_script_meta_records_model_prompt_hash_and_tokens(self, job):
        generate_script_for_job(job, client=StubLLMClient([llm_response()]))
        job.refresh_from_db()
        meta = job.script_meta
        assert meta["provider"] == "openrouter"
        assert meta["model"] == "anthropic/claude-sonnet-4.5"
        assert len(meta["prompt_sha256"]) == 64
        assert meta["prompt_tokens"] == 1200
        assert meta["completion_tokens"] == 800
        assert meta["total_tokens"] == 2000
        assert meta["checksum_sha256"]

    def test_creates_the_stage_checkpoint_asset(self, job):
        generate_script_for_job(job, client=StubLLMClient([llm_response()]))
        asset = VideoAsset.objects.get(job=job, kind=AssetKind.SCRIPT)
        segments = asset.metadata["segments"]
        assert len(segments) == 3
        # The voice stage reads narration + visual_prompt straight from here.
        assert segments[0]["narration"]
        assert segments[0]["visual_prompt"]
        assert asset.checksum_sha256

    def test_preference_constraints_reach_the_prompt(self, job):
        client = StubLLMClient([llm_response()])
        generate_script_for_job(job, client=client)
        user_message = client.calls[0][1]["content"]
        assert "travel" in user_message
        assert "politics" in user_message and "gambling" in user_message  # FR-34 banned topics
        assert "Dry, precise, no hype" in user_message  # FR-34 brand voice
        assert "180 seconds" in user_message  # FR-33 duration

    def test_job_without_content_preferences_is_rejected(self, job):
        job.preference = None
        job.save(update_fields=["preference"])
        with pytest.raises(JobNotReady):
            generate_script_for_job(job, client=StubLLMClient([llm_response()]))


class TestIdempotency:
    """NFR-25: an at-least-once redelivery must not re-invoke a paid provider."""

    def test_second_run_reuses_the_checkpoint_without_calling_the_llm(self, job):
        first_client = StubLLMClient([llm_response()])
        generate_script_for_job(job, client=first_client)
        job.refresh_from_db()

        second_client = StubLLMClient([])  # any call would raise IndexError
        result = generate_script_for_job(job, client=second_client)

        assert second_client.calls == []
        assert result.title == VALID_SCRIPT_PAYLOAD["title"]
        assert len(result.segments) == 3
        assert ApiUsageLog.objects.filter(job=job).count() == 1
        assert VideoAsset.objects.filter(job=job, kind=AssetKind.SCRIPT).count() == 1


class TestRecentTopicDeduplication:
    """FR-37."""

    def test_collects_recent_titles_from_the_same_preference(self, job):
        for index in range(3):
            VideoJobFactory(
                channel=job.channel,
                preference=job.preference,
                user=job.user,
                title=f"Previous video {index}",
            )
        titles = collect_recent_topics(job)
        assert len(titles) == 3
        assert job.title not in titles

    def test_recent_limit_is_configurable(self, job, settings):
        settings.SCRIPT_RECENT_TOPICS_LIMIT = 2
        for index in range(5):
            VideoJobFactory(
                channel=job.channel, preference=job.preference, user=job.user, title=f"Old {index}"
            )
        assert len(collect_recent_topics(job)) == 2

    def test_other_channels_history_does_not_leak_between_creators(self, job):
        VideoJobFactory(title="Someone else's video")  # different channel + preference
        assert collect_recent_topics(job) == []

    def test_recent_titles_are_injected_into_the_prompt(self, job):
        VideoJobFactory(
            channel=job.channel,
            preference=job.preference,
            user=job.user,
            title="A Weekend In Bilbao",
        )
        client = StubLLMClient([llm_response()])
        generate_script_for_job(job, client=client)
        assert "A Weekend In Bilbao" in client.calls[0][1]["content"]

    def test_near_duplicate_title_triggers_one_resample(self, job, settings):
        settings.SCRIPT_MAX_DEDUP_ATTEMPTS = 2
        VideoJobFactory(
            channel=job.channel,
            preference=job.preference,
            user=job.user,
            title=VALID_SCRIPT_PAYLOAD["title"],
        )
        second = json.loads(json.dumps(VALID_SCRIPT_PAYLOAD))
        second["title"] = "Rebuilding A 1970s Motorcycle Carburettor From Scratch"

        client = StubLLMClient([llm_response(), llm_response(second)])
        script = generate_script_for_job(job, client=client)

        assert len(client.calls) == 2
        assert script.title == second["title"]
        # The resample prompt must tell the model why it was rejected.
        assert "near-duplicate" in client.calls[1][1]["content"]
        # Both attempts are billed and logged (FR-51).
        assert ApiUsageLog.objects.filter(job=job).count() == 2

    def test_unique_title_does_not_resample(self, job):
        client = StubLLMClient([llm_response()])
        generate_script_for_job(job, client=client)
        assert len(client.calls) == 1

    def test_persistent_duplicate_is_kept_but_flagged(self, job, settings):
        settings.SCRIPT_MAX_DEDUP_ATTEMPTS = 2
        VideoJobFactory(
            channel=job.channel,
            preference=job.preference,
            user=job.user,
            title=VALID_SCRIPT_PAYLOAD["title"],
        )
        client = StubLLMClient([llm_response(), llm_response()])
        generate_script_for_job(job, client=client)

        job.refresh_from_db()
        assert job.script_meta["title_similarity_flagged"] is True
        assert job.script_meta["title_similarity_max"] >= 0.9


class TestCostAccounting:
    """FR-51 / FR-52."""

    def test_writes_one_usage_log_row_per_call(self, job):
        generate_script_for_job(job, client=StubLLMClient([llm_response()]))
        log = ApiUsageLog.objects.get(job=job)
        assert log.service == ServiceType.LLM
        assert log.provider == "openrouter"
        assert log.model == "anthropic/claude-sonnet-4.5"
        assert log.operation == "script_generation"
        assert log.units == Decimal("2000.0000")
        assert log.unit_type == "tokens"
        assert log.success is True
        assert log.latency_ms == 1234
        assert log.http_status == 200
        assert log.request_id == "gen-integration-1"

    def test_cost_is_computed_from_configured_prices(self, job):
        generate_script_for_job(job, client=StubLLMClient([llm_response()]))
        # 1200 in @ $0.003/1k + 800 out @ $0.015/1k = $0.0156
        assert ApiUsageLog.objects.get(job=job).cost_usd == Decimal("0.015600")

    def test_provider_reported_cost_overrides_the_price_table(self, job):
        generate_script_for_job(job, client=StubLLMClient([llm_response(cost="0.004321")]))
        assert ApiUsageLog.objects.get(job=job).cost_usd == Decimal("0.004321")

    def test_job_total_cost_is_rolled_up(self, job):
        generate_script_for_job(job, client=StubLLMClient([llm_response()]))
        job.refresh_from_db()
        assert job.total_cost_usd == Decimal("0.0156")

    def test_failed_call_still_records_a_usage_row(self, job):
        client = StubLLMClient([ProviderRateLimitError("429", retry_after_sec=10)])
        with pytest.raises(ProviderRateLimitError):
            generate_script_for_job(job, client=client)

        log = ApiUsageLog.objects.get(job=job)
        assert log.success is False
        assert log.error_code == "provider_rate_limited"
        assert log.cost_usd == Decimal("0")
        # Nothing was persisted to the job itself.
        job.refresh_from_db()
        assert job.script_text == ""
        assert not VideoAsset.objects.filter(job=job).exists()

    def test_cost_ceiling_stops_the_job(self, job, settings):
        settings.JOB_COST_CEILING_USD = "0.0001"
        with pytest.raises(CostCeilingExceeded):
            generate_script_for_job(job, client=StubLLMClient([llm_response()]))

    def test_ceiling_of_zero_disables_the_check(self, job, settings):
        settings.JOB_COST_CEILING_USD = "0"
        generate_script_for_job(job, client=StubLLMClient([llm_response()]))  # must not raise


# ---------------------------------------------------------------------------
# Script moderation
# ---------------------------------------------------------------------------
@pytest.fixture
def scripted_job(job):
    generate_script_for_job(job, client=StubLLMClient([llm_response()]))
    job.refresh_from_db()
    return job


class TestScriptModeration:
    def test_clean_script_passes_and_logs(self, scripted_job):
        client = StubModerationClient([moderation_payload({"violence": 0.001, "hate": 0.0005})])
        outcome = moderate_script_for_job(scripted_job, client=client)

        assert outcome.verdict == ModerationVerdict.PASS
        log = ModerationLog.objects.get(job=scripted_job)
        assert log.stage == ModerationStage.SCRIPT
        assert log.provider == "openai_moderation"
        assert log.verdict == ModerationVerdict.PASS
        assert log.categories["violence"] == 0.001
        assert log.threshold_config["block_threshold"] == 0.5
        assert log.raw_response["id"] == "modr-test-1"

    def test_the_full_script_text_is_what_gets_moderated(self, scripted_job):
        client = StubModerationClient([moderation_payload({"violence": 0.0})])
        moderate_script_for_job(scripted_job, client=client)
        assert "\n\n".join(client.calls[0]) == scripted_job.script_text

    def test_score_over_threshold_blocks(self, scripted_job):
        client = StubModerationClient([moderation_payload({"violence": 0.87}, flagged=True)])
        outcome = moderate_script_for_job(scripted_job, client=client)
        assert outcome.verdict == ModerationVerdict.BLOCK
        assert outcome.max_category == "violence"
        assert ModerationLog.objects.get(job=scripted_job).verdict == ModerationVerdict.BLOCK

    def test_threshold_is_read_from_provider_config(self, scripted_job):
        config = get_primary_config(ServiceType.MODERATION)
        config.config = {**config.config, "block_threshold": 0.05}
        config.save(update_fields=["config"])

        client = StubModerationClient([moderation_payload({"violence": 0.1})])
        assert moderate_script_for_job(scripted_job, client=client).verdict == ModerationVerdict.BLOCK

    def test_moderation_writes_a_usage_log(self, scripted_job):
        client = StubModerationClient([moderation_payload({"violence": 0.0})])
        moderate_script_for_job(scripted_job, client=client)
        log = ApiUsageLog.objects.get(job=scripted_job, operation="script_moderation")
        assert log.provider == "openai_moderation"
        assert log.units == Decimal("1.0000")
        assert log.unit_type == "requests"
        assert log.success is True

    def test_provider_failure_is_logged_and_reraised(self, scripted_job):
        client = StubModerationClient([ProviderRateLimitError("429")])
        with pytest.raises(ProviderRateLimitError):
            moderate_script_for_job(scripted_job, client=client)
        log = ApiUsageLog.objects.get(job=scripted_job, operation="script_moderation")
        assert log.success is False
        assert not ModerationLog.objects.filter(job=scripted_job).exists()

    def test_empty_script_is_rejected_before_calling_the_provider(self, job):
        client = StubModerationClient([])
        with pytest.raises(Exception) as exc_info:
            moderate_script_for_job(job, client=client)
        assert getattr(exc_info.value, "error_code", "") == "moderation_empty_input"


class TestVerdictToJobStatus:
    """SPEC 7.2 + FR-48."""

    def _outcome(self, verdict):
        from video_pipeline.services.script_moderation import ModerationOutcome

        return ModerationOutcome(
            verdict=verdict,
            max_category="violence",
            max_score=0.9,
            category_scores={"violence": 0.9},
            provider_flagged=verdict != ModerationVerdict.PASS,
            thresholds={"block_threshold": 0.5, "flag_threshold": 0.2, "category_thresholds": {}},
        )

    def test_pass_leaves_the_job_at_the_script_checkpoint(self, scripted_job):
        assert apply_verdict_to_job(scripted_job, self._outcome(ModerationVerdict.PASS)) == (
            JobStatus.SCRIPT_READY
        )
        scripted_job.refresh_from_db()
        assert scripted_job.status == JobStatus.SCRIPT_READY
        assert scripted_job.error_code == ""

    def test_flag_goes_to_the_human_moderator_queue(self, scripted_job):
        apply_verdict_to_job(scripted_job, self._outcome(ModerationVerdict.FLAG))
        scripted_job.refresh_from_db()
        assert scripted_job.status == JobStatus.MODERATION_REVIEW

    def test_block_goes_to_review_not_auto_reject_by_default(self, scripted_job):
        # FR-48: content that fails moderation is never auto-published AND never
        # auto-rejected — a moderator decides.
        apply_verdict_to_job(scripted_job, self._outcome(ModerationVerdict.BLOCK))
        scripted_job.refresh_from_db()
        assert scripted_job.status == JobStatus.MODERATION_REVIEW
        assert scripted_job.error_code == "script_moderation_flagged"
        assert "violence" in scripted_job.error_message

    def test_block_can_be_configured_to_auto_reject(self, scripted_job, settings):
        settings.MODERATION_AUTO_REJECT_ON_BLOCK = True
        apply_verdict_to_job(scripted_job, self._outcome(ModerationVerdict.BLOCK))
        scripted_job.refresh_from_db()
        assert scripted_job.status == JobStatus.MODERATION_REJECTED

    def test_flag_never_auto_rejects_even_with_the_flag_on(self, scripted_job, settings):
        settings.MODERATION_AUTO_REJECT_ON_BLOCK = True
        apply_verdict_to_job(scripted_job, self._outcome(ModerationVerdict.FLAG))
        scripted_job.refresh_from_db()
        assert scripted_job.status == JobStatus.MODERATION_REVIEW


# ---------------------------------------------------------------------------
# Celery task wiring
# ---------------------------------------------------------------------------
class TestCeleryTasks:
    def test_generate_script_task_writes_the_append_only_step_trail(self, job, monkeypatch):
        from video_pipeline import tasks
        from video_pipeline.services import script_generation

        monkeypatch.setattr(
            script_generation,
            "generate_script_for_job",
            lambda j, **kw: generate_script_for_job(j, client=StubLLMClient([llm_response()])),
        )
        result = tasks.generate_script.apply(args=[str(job.pk)], kwargs={"chain_next": False}).get()

        assert result["status"] == JobStatus.SCRIPT_READY
        steps = list(VideoJobStep.objects.filter(job=job, stage=Stage.SCRIPT).order_by("id"))
        assert [s.status for s in steps] == [StepStatus.STARTED, StepStatus.SUCCEEDED]
        assert steps[1].provider == "openrouter"
        assert steps[1].duration_ms is not None
        assert steps[1].cost_usd == Decimal("0.0156")
        # Append-only: the STARTED row was never mutated (SPEC 5.12).
        assert steps[0].finished_at is None

        job.refresh_from_db()
        assert job.status == JobStatus.SCRIPT_READY
        assert job.current_stage == Stage.SCRIPT
        assert job.started_at is not None

    def test_terminal_job_is_not_resurrected(self, job):
        from video_pipeline import tasks

        job.status = JobStatus.CANCELED
        job.save(update_fields=["status"])
        result = tasks.generate_script.apply(args=[str(job.pk)], kwargs={"chain_next": False}).get()
        assert result["skipped"] is True
        assert not VideoJobStep.objects.filter(job=job).exists()

    def test_moderate_content_task_records_steps_and_verdict(self, scripted_job, monkeypatch):
        from video_pipeline import tasks
        from video_pipeline.services import script_moderation

        client = StubModerationClient([moderation_payload({"violence": 0.9}, flagged=True)])
        original = script_moderation.moderate_script_for_job
        monkeypatch.setattr(
            script_moderation, "moderate_script_for_job", lambda j, **kw: original(j, client=client)
        )
        result = tasks.moderate_content.apply(
            args=[str(scripted_job.pk)], kwargs={"scope": ModerationStage.SCRIPT}
        ).get()

        assert result["verdict"] == ModerationVerdict.BLOCK
        assert result["status"] == JobStatus.MODERATION_REVIEW
        steps = list(
            VideoJobStep.objects.filter(job=scripted_job, stage=Stage.MODERATION).order_by("id")
        )
        assert [s.status for s in steps] == [StepStatus.STARTED, StepStatus.SUCCEEDED]

        scripted_job.refresh_from_db()
        assert scripted_job.status == JobStatus.MODERATION_REVIEW
        assert ModerationLog.objects.filter(job=scripted_job).count() == 1

    def test_visual_moderation_scope_is_still_a_stub(self, scripted_job):
        """`scope="visual"` has no place in SPEC 7.1 (only script and final moderation
        gates exist) and stays an explicit stub. `Task.apply()`'s `throw=False` only
        suppresses the *first* eager retry attempt — Celery's internal eager-retry
        loop re-enters with `throw` back at `CELERY_TASK_EAGER_PROPAGATES` (True in
        tests) on the next attempt, so `pytest.raises` is the reliable way to assert
        this, not `result.state`.
        """
        from celery.exceptions import Retry

        from video_pipeline import tasks

        with pytest.raises(Retry):
            tasks.moderate_content.apply(args=[str(scripted_job.pk)], kwargs={"scope": ModerationStage.VISUAL})

        step = VideoJobStep.objects.filter(
            job=scripted_job, stage=Stage.MODERATION, status=StepStatus.FAILED
        ).first()
        assert step is not None
        assert step.error_code == "not_implemented"

    def test_voice_stage_fails_cleanly_when_tts_not_configured(self, scripted_job):
        """Stage 3 is wired (video_pipeline.services.voice_generation); with no
        `api_credentials_config` row for TTS in the test DB it fails fast and
        cleanly rather than retrying (ProviderNotConfigured is not retryable).
        """
        from video_pipeline import tasks

        with pytest.raises(ProviderNotConfigured):
            tasks.generate_voice.apply(args=[str(scripted_job.pk)]).get()

        scripted_job.refresh_from_db()
        assert scripted_job.status == JobStatus.FAILED
        assert scripted_job.error_code == "provider_not_configured"
        step = VideoJobStep.objects.filter(
            job=scripted_job, stage=Stage.VOICE, status=StepStatus.FAILED
        ).first()
        assert step is not None
        assert step.error_code == "provider_not_configured"
