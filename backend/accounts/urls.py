"""SPEC 6: Auth + Me endpoint groups."""
from django.urls import path

from accounts import views
from accounts.consents import MyConsentsView
from core.stub_views import NotImplementedStubView

app_name = "accounts"

urlpatterns = [
    # --- Auth ---
    path("auth/register", views.RegisterView.as_view(), name="register"),
    path("auth/login", views.LoginView.as_view(), name="login"),
    path("auth/refresh", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="logout"),
    path("auth/verify-email", views.VerifyEmailView.as_view(), name="verify-email"),
    path("auth/password/reset", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "auth/password/reset/confirm",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("auth/google", views.GoogleAuthView.as_view(), name="google-auth"),
    path(
        "auth/2fa/enable",
        NotImplementedStubView.as_view(feature_name="TOTP 2FA enable (FR-9)"),
        name="2fa-enable",
    ),
    path(
        "auth/2fa/verify",
        NotImplementedStubView.as_view(feature_name="TOTP 2FA verify (FR-9)"),
        name="2fa-verify",
    ),
    # --- Me ---
    path("me", views.MeView.as_view(), name="me"),
    path(
        "me/sessions",
        NotImplementedStubView.as_view(feature_name="active session listing"),
        name="me-sessions",
    ),
    path(
        "me/sessions/<uuid:session_id>",
        NotImplementedStubView.as_view(feature_name="session revocation"),
        name="me-session-detail",
    ),
    # --- Track A ---
    path("me/consents", MyConsentsView.as_view(), name="me-consents"),
]
