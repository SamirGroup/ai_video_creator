import pytest
from accounts.tests.factories import UserFactory
from audit.models import AuditLog
from rest_framework.test import APIClient

from adminpanel.models import Partner, PartnerBanner

pytestmark = pytest.mark.django_db
DATA = {
    "name": "Example Partner",
    "image_url": "https://example.com/logo.svg",
    "link_url": "https://example.com/signup?ref=creator%2Bai&utm_source=site#offer",
    "caption": "Hamkor taklifi",
    "sort_order": 2,
    "is_active": True,
    "is_affiliate": True,
}


def admin_client():
    c = APIClient()
    c.force_authenticate(UserFactory(is_superuser=True, is_totp_enabled=True))
    return c


def test_partner_crud_referral_preservation_visibility_and_audit():
    client = admin_client()
    response = client.post("/api/v1/admin/partners", DATA, format="json")
    assert response.status_code == 201, response.data
    pk = response.data["id"]
    public = APIClient()
    data = public.get("/api/v1/public/partners").data
    assert data["partners"][0]["link_url"] == DATA["link_url"]
    assert data["partners"][0]["is_affiliate"] is True
    assert (
        client.patch(
            f"/api/v1/admin/partners/{pk}", {"is_active": False}, format="json"
        ).status_code
        == 200
    )
    assert public.get("/api/v1/public/partners").data["partners"] == []
    assert client.delete(f"/api/v1/admin/partners/{pk}").status_code == 204
    assert not Partner.objects.exists()
    assert AuditLog.objects.filter(resource_type="partner").count() == 3


def test_banner_controls_and_ordering():
    client = admin_client()
    for name, order in [("Last", 8), ("First", 1)]:
        Partner.objects.create(**{**DATA, "name": name, "sort_order": order})
    public = APIClient()
    assert [
        p["name"] for p in public.get("/api/v1/public/partners").data["partners"]
    ] == ["First", "Last"]
    response = client.patch(
        "/api/v1/admin/partners/banner",
        {
            "enabled": False,
            "title": "Hamkorlar",
            "animation_enabled": False,
            "animation_seconds": 60,
        },
        format="json",
    )
    assert response.status_code == 200
    data = public.get("/api/v1/public/partners").data
    assert not data["banner"]["enabled"] and data["partners"] == []
    assert Partner.objects.filter(is_active=True).count() == 2
    assert (
        client.patch(
            "/api/v1/admin/partners/banner", {"animation_seconds": 0}, format="json"
        ).status_code
        == 400
    )
    assert PartnerBanner.objects.get(pk=1).animation_seconds == 60


@pytest.mark.parametrize("field", ["image_url", "link_url"])
@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://example.com",
        "https://user:pw@example.com",
        "https://127.0.0.1/a",
        "https://169.254.169.254/a",
        "https://localhost/a",
    ],
)
def test_unsafe_partner_urls_rejected(field, url):
    assert (
        admin_client()
        .post("/api/v1/admin/partners", {**DATA, field: url}, format="json")
        .status_code
        == 400
    )
    assert not Partner.objects.exists()


def test_anonymous_creator_and_admin_without_2fa_cannot_write(settings):
    settings.STAFF_2FA_REQUIRED = True
    client = APIClient()
    assert client.post("/api/v1/admin/partners", DATA, format="json").status_code == 401
    for user in [UserFactory(), UserFactory(is_superuser=True, is_totp_enabled=False)]:
        client.force_authenticate(user)
        assert (
            client.post("/api/v1/admin/partners", DATA, format="json").status_code
            == 403
        )
        assert (
            client.patch(
                "/api/v1/admin/partners/banner", {"enabled": False}, format="json"
            ).status_code
            == 403
        )
    assert (
        APIClient().post("/api/v1/public/partners", DATA, format="json").status_code
        == 405
    )
