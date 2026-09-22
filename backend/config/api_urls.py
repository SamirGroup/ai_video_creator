"""Aggregates every app's `/api/v1/...` URL group (SPEC section 6)."""

from django.urls import include, path

urlpatterns = [
    path("", include("virtual_numbers.urls")),
    path("", include("telegram_integration.urls")),
    path("", include("accounts.urls")),
    path("", include("channels.urls")),
    path("", include("billing.urls")),
    path("", include("contracts.urls")),
    path("", include("video_pipeline.urls")),
    path("", include("moderation.urls")),
    path("", include("revenue.urls")),
    path("", include("notifications.urls")),
    path("", include("adminpanel.urls")),
]
