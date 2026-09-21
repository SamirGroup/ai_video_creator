"""The 2FA exemption is what stands between staff and an unprotected login, so
its boundaries are worth pinning down: who it covers, and when it lapses."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from accounts.test_access import temporary_2fa_exemption
from accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

FUTURE = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()


@pytest.fixture
def superuser():
    user = UserFactory(email="super@example.com")
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    return user


def _env(monkeypatch, ids: str, until: str) -> None:
    monkeypatch.setenv("TEMP_2FA_BYPASS_USER_ID", ids)
    monkeypatch.setenv("TEMP_2FA_BYPASS_UNTIL", until)


class TestTemporary2FAExemption:
    def test_exempts_a_listed_superuser_before_the_deadline(self, monkeypatch, superuser):
        _env(monkeypatch, str(superuser.pk), FUTURE)
        assert temporary_2fa_exemption(superuser) is True

    def test_exempts_every_id_in_a_comma_separated_list(self, monkeypatch, superuser):
        other = UserFactory(email="other@example.com")
        other.is_superuser = True
        other.save(update_fields=["is_superuser"])

        _env(monkeypatch, f"{superuser.pk} , {other.pk}", FUTURE)

        assert temporary_2fa_exemption(superuser) is True
        assert temporary_2fa_exemption(other) is True

    def test_does_not_exempt_an_unlisted_superuser(self, monkeypatch, superuser):
        stranger = UserFactory(email="stranger@example.com")
        stranger.is_superuser = True
        stranger.save(update_fields=["is_superuser"])

        _env(monkeypatch, str(superuser.pk), FUTURE)

        assert temporary_2fa_exemption(stranger) is False

    def test_lapses_once_the_deadline_passes(self, monkeypatch, superuser):
        _env(monkeypatch, str(superuser.pk), PAST)
        assert temporary_2fa_exemption(superuser) is False

    def test_refuses_a_deadline_without_a_timezone(self, monkeypatch, superuser):
        # A naive deadline is ambiguous, so it must not be read as permission.
        _env(monkeypatch, str(superuser.pk), "2099-01-01T00:00:00")
        assert temporary_2fa_exemption(superuser) is False

    def test_refuses_an_unparseable_deadline(self, monkeypatch, superuser):
        _env(monkeypatch, str(superuser.pk), "whenever")
        assert temporary_2fa_exemption(superuser) is False

    def test_never_exempts_a_non_superuser(self, monkeypatch):
        creator = UserFactory(email="creator@example.com")
        _env(monkeypatch, str(creator.pk), FUTURE)
        assert temporary_2fa_exemption(creator) is False

    @pytest.mark.parametrize("ids", ["", "   ", " , , "])
    def test_empty_configuration_exempts_nobody(self, monkeypatch, superuser, ids):
        _env(monkeypatch, ids, FUTURE)
        assert temporary_2fa_exemption(superuser) is False

    def test_missing_configuration_exempts_nobody(self, monkeypatch, superuser):
        monkeypatch.delenv("TEMP_2FA_BYPASS_USER_ID", raising=False)
        monkeypatch.delenv("TEMP_2FA_BYPASS_UNTIL", raising=False)
        assert temporary_2fa_exemption(superuser) is False
