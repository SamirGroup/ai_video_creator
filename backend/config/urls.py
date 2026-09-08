"""Root URLconf (SPEC section 6: base `/api/v1/`)."""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Docker/compose healthcheck target (see docker-compose.yml, backend/Dockerfile).
    path("api/health/", core_views.health_ready, name="health-combined"),
    # SPEC 6 "System" group.
    path("health/", include("core.urls")),
    path("api/v1/", include("config.api_urls")),
    # Signed local media (only active with LocalFileStorage — see core.storage).
    path("internal/media/", core_views.serve_local_media, name="local-media"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
