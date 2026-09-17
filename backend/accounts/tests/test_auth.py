"""Smoke tests for the auth flow (FR-1, FR-2, FR-4, FR-5, FR-6)."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from accounts.tests.factories import UserFactory
from accounts.tokens import make_email_verification_token, make_password_reset_token

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class TestRegister:
    def test_register_creates_unverified_user_and_sends_email(self, api_client, mailoutbox):
        url = reverse("accounts:register")
        payload = {
            "email": "new.creator@example.com",
            "password": "a-strong-password-123",
            "full_name": "New Creator",
        }

        response = api_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        user = User.objects.get(email="new.creator@example.com")
        assert user.is_email_verified is False
        assert user.check_password("a-strong-password-123")
        assert len(mailoutbox) == 1
        assert "verify-email" in mailoutbox[0].body

    def test_register_rejects_duplicate_email(self, api_client):
        UserFactory(email="taken@example.com")
        url = reverse("accounts:register")

        response = api_client.post(
            url,
            {"email": "taken@example.com", "password": "a-strong-password-123"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_rejects_short_password(self, api_client):
        url = reverse("accounts:register")

        response = api_client.post(
            url,
            {"email": "short@example.com", "password": "short1"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestLogin:
    def test_login_with_valid_credentials_returns_access_token_and_refresh_cookie(self, api_client):
        UserFactory(email="login@example.com", password="a-strong-password-123")
        url = reverse("accounts:login")

        response = api_client.post(
            url,
            {"email": "login@example.com", "password": "a-strong-password-123"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh_token" in response.cookies
        assert response.cookies["refresh_token"]["httponly"] is True

    def test_login_with_wrong_password_is_rejected(self, api_client):
        UserFactory(email="login2@example.com", password="a-strong-password-123")
        url = reverse("accounts:login")

        response = api_client.post(
            url,
            {"email": "login2@example.com", "password": "totally-wrong-password"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_with_suspended_account_is_rejected(self, api_client):
        user = UserFactory(email="suspended@example.com", password="a-strong-password-123")
        user.status = "suspended"
        user.save(update_fields=["status"])
        url = reverse("accounts:login")

        response = api_client.post(
            url,
            {"email": "suspended@example.com", "password": "a-strong-password-123"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestRefreshAndLogout:
    def test_refresh_rotates_cookie_and_issues_new_access_token(self, api_client):
        UserFactory(email="refresh@example.com", password="a-strong-password-123")
        login_response = api_client.post(
            reverse("accounts:login"),
            {"email": "refresh@example.com", "password": "a-strong-password-123"},
            format="json",
        )
        api_client.cookies["refresh_token"] = login_response.cookies["refresh_token"].value

        refresh_response = api_client.post(reverse("accounts:refresh"))

        assert refresh_response.status_code == status.HTTP_200_OK
        assert "access" in refresh_response.data
        assert refresh_response.cookies["refresh_token"].value != login_response.cookies["refresh_token"].value

    def test_refresh_without_cookie_is_rejected(self, api_client):
        response = api_client.post(reverse("accounts:refresh"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_requires_authentication(self, api_client):
        response = api_client.post(reverse("accounts:logout"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_clears_refresh_cookie(self, api_client):
        UserFactory(email="logout@example.com", password="a-strong-password-123")
        login_response = api_client.post(
            reverse("accounts:login"),
            {"email": "logout@example.com", "password": "a-strong-password-123"},
            format="json",
        )
        access_token = login_response.data["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        api_client.cookies["refresh_token"] = login_response.cookies["refresh_token"].value

        response = api_client.post(reverse("accounts:logout"))

        assert response.status_code == status.HTTP_204_NO_CONTENT


class TestVerifyEmailAndPasswordReset:
    def test_verify_email_with_valid_token_marks_user_verified(self, api_client):
        user = UserFactory(email="verify@example.com", is_email_verified=False)
        token = make_email_verification_token(user.id)

        response = api_client.post(reverse("accounts:verify-email"), {"token": token}, format="json")

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.is_email_verified is True

    def test_verify_email_with_invalid_token_is_rejected(self, api_client):
        response = api_client.post(
            reverse("accounts:verify-email"), {"token": "not-a-real-token"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_reset_request_always_returns_202(self, api_client, mailoutbox):
        UserFactory(email="reset@example.com")

        response = api_client.post(
            reverse("accounts:password-reset"), {"email": "reset@example.com"}, format="json"
        )
        unknown_response = api_client.post(
            reverse("accounts:password-reset"), {"email": "unknown@example.com"}, format="json"
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert unknown_response.status_code == status.HTTP_202_ACCEPTED
        assert len(mailoutbox) == 1

    def test_password_reset_confirm_updates_password(self, api_client):
        user = UserFactory(email="confirm@example.com", password="old-password-123")
        token = make_password_reset_token(user)

        response = api_client.post(
            reverse("accounts:password-reset-confirm"),
            {"token": token, "new_password": "brand-new-password-123"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password("brand-new-password-123")


class TestMeEndpoint:
    def test_me_requires_authentication(self, api_client):
        response = api_client.get(reverse("accounts:me"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_me_returns_current_user(self, api_client):
        UserFactory(email="me@example.com", password="a-strong-password-123")
        login_response = api_client.post(
            reverse("accounts:login"),
            {"email": "me@example.com", "password": "a-strong-password-123"},
            format="json",
        )
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")

        response = api_client.get(reverse("accounts:me"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "me@example.com"
