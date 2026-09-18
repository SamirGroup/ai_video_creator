from django.urls import path

from adminpanel import views
from adminpanel.auth_logos import PublicAuthLogos, AdminAuthLogos, AdminAuthLogoDetail

app_name = "adminpanel"

urlpatterns = [
    path("public/auth-logos", PublicAuthLogos.as_view()),
    path("admin/auth-logos", AdminAuthLogos.as_view()),
    path("admin/auth-logos/<int:pk>", AdminAuthLogoDetail.as_view()),
    # --- Users (FR-79) ---
    path("admin/users", views.AdminUserListView.as_view(), name="user-list"),
    path("admin/users/<uuid:user_id>", views.AdminUserDetailView.as_view(), name="user-detail"),
    path("admin/users/<uuid:user_id>/suspend", views.AdminUserSuspendView.as_view(), name="user-suspend"),
    path("admin/users/<uuid:user_id>/reactivate", views.AdminUserReactivateView.as_view(), name="user-reactivate"),
    path("admin/users/<uuid:user_id>/roles", views.AdminUserRolesView.as_view(), name="user-roles"),
    # --- Video jobs (FR-80) ---
    path("admin/videos", views.AdminVideoJobListView.as_view(), name="video-list"),
    path("admin/videos/<uuid:job_id>/retry", views.AdminVideoJobRetryView.as_view(), name="video-retry"),
    path("admin/videos/<uuid:job_id>/cancel", views.AdminVideoJobCancelView.as_view(), name="video-cancel"),
    path("admin/queues", views.AdminQueuesView.as_view(), name="queues"),
    # --- Config (FR-83, FR-84) ---
    path("admin/plans", views.AdminPlanListView.as_view(), name="plan-list"),
    path("admin/plans/<uuid:plan_id>", views.AdminPlanDetailView.as_view(), name="plan-detail"),
    path("admin/providers", views.AdminProviderListView.as_view(), name="provider-list"),
    path("admin/providers/<uuid:provider_id>", views.AdminProviderDetailView.as_view(), name="provider-detail"),
    path(
        "admin/providers/<uuid:provider_id>/rotate-secret",
        views.AdminProviderRotateSecretView.as_view(),
        name="provider-rotate-secret",
    ),
]
