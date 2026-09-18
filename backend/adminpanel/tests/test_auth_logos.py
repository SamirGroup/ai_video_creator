import pytest
from rest_framework.test import APIClient
from accounts.tests.factories import UserFactory
from adminpanel.models import AuthLogo
from audit.models import AuditLog

pytestmark = pytest.mark.django_db
DATA = {
    "name": "Example AI",
    "image_url": "https://example.com/logo.png",
    "link_url": "https://example.com/ai",
    "sort_order": 2,
    "is_active": True,
}


def test_superadmin_crud_and_public_visibility():
    client = APIClient()
    client.force_authenticate(UserFactory(is_superuser=True, is_totp_enabled=True))
    response = client.post("/api/v1/admin/auth-logos", DATA)
    assert response.status_code == 201
    pk = response.data["id"]
    public = APIClient()
    assert public.get("/api/v1/public/auth-logos").data[0]["name"] == "Example AI"
    assert (
        client.patch(
            f"/api/v1/admin/auth-logos/{pk}", {"name": "Replaced", "is_active": False}
        ).status_code
        == 200
    )
    assert public.get("/api/v1/public/auth-logos").data == []
    assert client.delete(f"/api/v1/admin/auth-logos/{pk}").status_code == 204
    assert not AuthLogo.objects.exists()
    assert AuditLog.objects.filter(resource_type="auth_logo").count() == 3


@pytest.mark.parametrize(
    "superuser,totp", [(False, False), (False, True), (True, False)]
)
def test_only_superadmin_with_two_factor_can_write(superuser, totp):
    client = APIClient()
    client.force_authenticate(UserFactory(is_superuser=superuser, is_totp_enabled=totp))
    assert client.post("/api/v1/admin/auth-logos", DATA).status_code == 403


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "http://example.com", "https://user:password@example.com"],
)
def test_reject_unsafe_links(url):
    client = APIClient()
    client.force_authenticate(UserFactory(is_superuser=True, is_totp_enabled=True))
    assert (
        client.post("/api/v1/admin/auth-logos", {**DATA, "link_url": url}).status_code
        == 400
    )
