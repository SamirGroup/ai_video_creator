import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from content_planning.proposals import (
    create_proposal,
    prepare_proposal,
    approve_proposal,
    proposal_slots,
)
from video_pipeline.models import VideoJob
from video_pipeline.services.preferences import job_preferences
from video_pipeline.tests.factories import ContentPreferenceFactory
from video_pipeline.tests.fixtures import llm_config

pytestmark = pytest.mark.django_db


@pytest.fixture
def preference():
    return ContentPreferenceFactory()


@pytest.fixture
def plan(preference, monkeypatch):
    monkeypatch.setattr(
        "content_planning.proposals.assert_generation_allowed", lambda user: None
    )
    return create_proposal(
        preference.user,
        preference.channel,
        request_key=uuid.uuid4(),
        horizon="weekly",
        count=2,
    )


def prepare(plan, monkeypatch):
    monkeypatch.setattr(
        "content_planning.proposals.get_primary_config", lambda service: llm_config()
    )
    response = SimpleNamespace(
        content=json.dumps(
            {
                "summary": "Research summary",
                "items": [
                    {
                        "title": "Original topic one",
                        "brief": "Specific brief one",
                        "rationale": "Reason one",
                    },
                    {
                        "title": "Original topic two",
                        "brief": "Specific brief two",
                        "rationale": "Reason two",
                    },
                ],
            }
        ),
        provider_cost_usd=Decimal(".02"),
        total_tokens=100,
        request_id="plan-test",
    )
    client = SimpleNamespace(chat_completion=lambda **kwargs: response)
    prepare_proposal(
        plan.pk, research={"source": "youtube_data_api", "videos": []}, client=client
    )
    plan.refresh_from_db()
    return plan


def test_no_jobs_before_explicit_approval_and_idempotent_selection(plan, monkeypatch):
    prepare(plan, monkeypatch)
    assert plan.status == "ready"
    assert not VideoJob.objects.exists()
    first, second = list(plan.items.all())
    result = approve_proposal(plan.user, plan.pk, [first.pk])
    assert result.status == "approved"
    assert VideoJob.objects.count() == 1
    job = VideoJob.objects.get()
    assert job.status == "scheduled"
    assert job.generation_context["title"] == first.title
    assert job.scheduled_for == first.scheduled_for
    approve_proposal(plan.user, plan.pk, [first.pk])
    assert VideoJob.objects.count() == 1
    with pytest.raises(ValidationError):
        approve_proposal(plan.user, plan.pk, [second.pk])


def test_approved_preference_snapshot_survives_channel_edits(
    plan, preference, monkeypatch
):
    prepare(plan, monkeypatch)
    approve_proposal(plan.user, plan.pk, [plan.items.first().pk])
    preference.language = "fr"
    preference.video_duration_sec = 60
    preference.save()
    job = VideoJob.objects.get()
    assert job_preferences(job).language == "en"
    assert job_preferences(job).video_duration_sec == 180


def test_request_key_cannot_be_reused_for_other_proposal(plan):
    assert (
        create_proposal(
            plan.user,
            plan.channel,
            request_key=plan.request_key,
            horizon="weekly",
            count=2,
        ).pk
        == plan.pk
    )
    with pytest.raises(ValidationError):
        create_proposal(
            plan.user,
            plan.channel,
            request_key=plan.request_key,
            horizon="daily",
            count=1,
        )


def test_foreign_item_is_not_accepted(plan, monkeypatch):
    prepare(plan, monkeypatch)
    with pytest.raises(ValidationError):
        approve_proposal(plan.user, plan.pk, [uuid.uuid4()])
    assert not VideoJob.objects.exists()


def test_duplicate_delivery_does_not_call_provider_again(plan, monkeypatch):
    prepare(plan, monkeypatch)
    prepare_proposal(
        plan.pk,
        client=SimpleNamespace(
            chat_completion=lambda **kw: pytest.fail("duplicate provider call")
        ),
    )
    assert plan.items.count() == 2


def test_plan_api_is_owner_scoped_and_approved_items_are_immutable(plan, monkeypatch):
    prepare(plan, monkeypatch)
    stranger = ContentPreferenceFactory().user
    client = APIClient()
    client.force_authenticate(stranger)
    assert client.get(f"/api/v1/content-plans/{plan.pk}").status_code == 404
    client.force_authenticate(plan.user)
    item = plan.items.first()
    assert (
        client.patch(
            f"/api/v1/content-plans/{plan.pk}/items/{item.pk}",
            {"title": "Edited"},
            format="json",
        ).status_code
        == 200
    )
    approve_proposal(plan.user, plan.pk, [item.pk])
    assert (
        client.patch(
            f"/api/v1/content-plans/{plan.pk}/items/{item.pk}",
            {"title": "Changed after approval"},
            format="json",
        ).status_code
        == 400
    )


def test_slots_are_aware_ordered_and_future(plan):
    slots = proposal_slots(plan)
    assert all(timezone.is_aware(slot) and slot > timezone.now() for slot in slots)
    assert len(set(slots)) == 2
    assert slots == sorted(slots)
