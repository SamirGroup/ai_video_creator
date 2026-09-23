import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from accounts.models import Role, UserRole
from accounts.tests.factories import UserFactory
from content_planning.assistant import respond
from content_planning.assistant_models import (
    AssistantPolicy,
    AssistantProfile,
    AssistantTurn,
)
from rest_framework.test import APIClient
from video_pipeline.tests.fixtures import llm_config

pytestmark = pytest.mark.django_db


def client_for(user):
    role, _ = Role.objects.get_or_create(code="creator", defaults={"name": "Creator"})
    UserRole.objects.get_or_create(user=user, role=role)
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_anonymous_and_creator_cannot_access_admin():
    assert APIClient().get("/api/v1/me/assistant").status_code == 401
    client = client_for(UserFactory())
    assert client.get("/api/v1/admin/assistant").status_code == 403


def test_profile_history_are_tenant_scoped():
    one, two = UserFactory(), UserFactory()
    AssistantTurn.objects.create(
        user=two,
        request_key=uuid.uuid4(),
        question="private two",
        answer="private answer",
    )
    AssistantProfile.objects.create(user=two, goal="private goal")
    client = client_for(one)
    response = client.get("/api/v1/me/assistant")
    assert response.status_code == 200
    assert response.data["turns"] == []
    assert response.data["profile"]["goal"] == ""
    assert (
        client.patch(
            "/api/v1/me/assistant",
            {"goal": "my goal", "timezone": "Invalid/Zone"},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.patch(
            "/api/v1/me/assistant",
            {"goal": "my goal", "timezone": "Asia/Dubai"},
            format="json",
        ).status_code
        == 200
    )
    assert AssistantProfile.objects.get(user=two).goal == "private goal"


def test_disabled_provider_no_paid_request():
    client = client_for(UserFactory())
    AssistantPolicy.objects.create(pk=1, enabled=False)
    with patch("content_planning.assistant_views.respond.apply_async") as dispatch:
        result = client.post(
            "/api/v1/me/assistant",
            {"message": "hello", "request_key": str(uuid.uuid4())},
            format="json",
        )
    assert result.status_code == 503
    assert not dispatch.called
    assert not AssistantTurn.objects.exists()


def test_idempotent_submission_and_daily_limit():
    user = UserFactory()
    client = client_for(user)
    AssistantPolicy.objects.create(pk=1, daily_message_limit=1)
    key = str(uuid.uuid4())
    with (
        patch("content_planning.assistant_views.get_primary_config"),
        patch("content_planning.assistant_views.ensure_provider_ready"),
        patch("content_planning.assistant_views.respond.apply_async") as dispatch,
    ):
        first = client.post(
            "/api/v1/me/assistant",
            {"message": "hello", "request_key": key},
            format="json",
        )
        second = client.post(
            "/api/v1/me/assistant",
            {"message": "hello", "request_key": key},
            format="json",
        )
        limited = client.post(
            "/api/v1/me/assistant",
            {"message": "another", "request_key": str(uuid.uuid4())},
            format="json",
        )
    assert first.status_code == 202
    assert first.data["id"] == second.data["id"]
    assert dispatch.call_count == 1
    assert limited.status_code == 400


def test_response_uses_only_owner_context_and_records_cost():
    user, other = UserFactory(), UserFactory()
    AssistantProfile.objects.create(user=other, goal="DO NOT LEAK")
    turn = AssistantTurn.objects.create(
        user=user, request_key=uuid.uuid4(), question="Help me"
    )
    result = SimpleNamespace(
        content="Connect your channel.",
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120,
        provider_cost_usd=Decimal(".01"),
        request_id="request",
    )
    with (
        patch(
            "content_planning.assistant.get_primary_config", return_value=llm_config()
        ),
        patch("content_planning.assistant.ensure_provider_ready"),
        patch("content_planning.assistant.get_llm_client") as client,
        patch(
            "content_planning.assistant.record_api_usage", return_value=object()
        ) as usage,
    ):
        client.return_value.chat_completion.return_value = result
        respond(str(turn.pk))
        respond(str(turn.pk))
        assert client.return_value.chat_completion.call_count == 1
        assert "DO NOT LEAK" not in str(client.return_value.chat_completion.call_args)
        assert usage.call_args.kwargs["user"] == user
    turn.refresh_from_db()
    assert turn.status == "completed"
    assert turn.cost_usd == Decimal(".01")


def test_provider_error_is_redacted():
    turn = AssistantTurn.objects.create(
        user=UserFactory(), request_key=uuid.uuid4(), question="hello"
    )
    with patch(
        "content_planning.assistant.get_primary_config",
        side_effect=RuntimeError("sk_secret"),
    ):
        respond(str(turn.pk))
    turn.refresh_from_db()
    assert turn.status == "failed"
    assert "sk_secret" not in turn.error_code + turn.answer


def test_budget_failure_never_calls_model():
    from rest_framework.exceptions import PermissionDenied

    turn = AssistantTurn.objects.create(
        user=UserFactory(), request_key=uuid.uuid4(), question="hello"
    )
    with (
        patch(
            "content_planning.assistant.get_primary_config", return_value=llm_config()
        ),
        patch("content_planning.assistant.ensure_provider_ready"),
        patch(
            "content_planning.assistant.hold_operation",
            side_effect=PermissionDenied("balance"),
        ),
        patch("content_planning.assistant.get_llm_client") as client,
    ):
        respond(str(turn.pk))
    assert not client.called
    turn.refresh_from_db()
    assert turn.status == "failed"


def test_admin_policy_update_audited(settings):
    from audit.models import AuditLog

    settings.STAFF_2FA_REQUIRED = False
    user = UserFactory(is_superuser=True)
    client = APIClient()
    client.force_authenticate(user)
    result = client.patch(
        "/api/v1/admin/assistant",
        {"enabled": False, "daily_message_limit": 5},
        format="json",
    )
    assert result.status_code == 200
    assert AssistantPolicy.objects.get(pk=1).enabled is False
    assert AuditLog.objects.filter(action="assistant.policy.updated").exists()
    dashboard = client.get("/api/v1/admin/assistant")
    assert dashboard.status_code == 200
    assert dashboard.data["users"] >= 1
    assert isinstance(dashboard.data["integrations"], list)


def test_stale_turn_can_be_recovered():
    from datetime import timedelta

    from django.utils import timezone

    user = UserFactory()
    client = client_for(user)
    turn = AssistantTurn.objects.create(
        user=user, request_key=uuid.uuid4(), question="hello"
    )
    AssistantTurn.objects.filter(pk=turn.pk).update(
        created_at=timezone.now() - timedelta(minutes=11)
    )
    assert client.get("/api/v1/me/assistant").status_code == 200
    turn.refresh_from_db()
    assert turn.status == "failed"
