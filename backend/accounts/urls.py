"""SPEC 6: Auth + Me endpoint groups."""

from django.urls import path

from accounts import views
from accounts.consents import MyConsentsView
from accounts.data_rights import (
    DataDeleteCancelView,
    DataDeleteView,
    DataExportDetailView,
    DataExportView,
)
from accounts.sessions import SessionDetailView, SessionListView
from accounts.twofactor import (
    TwoFactorEnableView,
    TwoFactorLoginView,
    TwoFactorVerifyView,
)

app_name = "accounts"

urlpatterns = [
    path(
        "public/config", views.PublicConfigurationView.as_view(), name="public-config"
    ),
    # --- Auth ---
    path("auth/register", views.RegisterView.as_view(), name="register"),
    path("auth/login", views.LoginView.as_view(), name="login"),
    path("auth/refresh", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="logout"),
    path("auth/verify-email", views.VerifyEmailView.as_view(), name="verify-email"),
    path(
        "auth/password/reset",
        views.PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "auth/password/reset/confirm",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("auth/google", views.GoogleAuthView.as_view(), name="google-auth"),
    path(
        "auth/2fa/enable",
        TwoFactorEnableView.as_view(),
        name="2fa-enable",
    ),
    path(
        "auth/2fa/verify",
        TwoFactorVerifyView.as_view(),
        name="2fa-verify",
    ),
    # --- Me ---
    path("me", views.MeView.as_view(), name="me"),
    path(
        "me/sessions",
        SessionListView.as_view(),
        name="me-sessions",
    ),
    path(
        "me/sessions/<uuid:session_id>",
        SessionDetailView.as_view(),
        name="me-session-detail",
    ),
    # --- Track A ---
    path("me/consents", MyConsentsView.as_view(), name="me-consents"),
    path("auth/2fa/login", TwoFactorLoginView.as_view(), name="2fa-login"),
    path("me/data/export", DataExportView.as_view(), name="data-export"),
    path(
        "me/data/export/<uuid:request_id>",
        DataExportDetailView.as_view(),
        name="data-export-detail",
    ),
    path("me/data/delete", DataDeleteView.as_view(), name="data-delete"),
    path(
        "me/data/delete/cancel",
        DataDeleteCancelView.as_view(),
        name="data-delete-cancel",
    ),
]
