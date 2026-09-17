from __future__ import annotations

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.cookies import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    set_refresh_cookie,
)
from accounts.emails import send_password_reset_email, send_verification_email
from accounts.google_oauth import GoogleIDTokenError, verify_google_id_token
from accounts.models import User
from accounts.serializers import (
    GoogleAuthSerializer,
    LoginSerializer,
    MeUpdateSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)
from accounts.tokens import (
    make_email_verification_token,
    make_password_reset_token,
    password_reset_token_generator,
    read_email_verification_token,
    read_password_reset_token,
)

logger = logging.getLogger("accounts.views")


class RegisterThrottle(AnonRateThrottle):
    scope = "register"


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"


def _issue_tokens_response(
    user: User, status_code: int = status.HTTP_200_OK, request=None
) -> Response:
    refresh = RefreshToken.for_user(user)
    # --- Track E --- FR-5: remember device metadata for GET /me/sessions.
    if request is not None:
        from accounts.sessions import record_session

        record_session(user, refresh, request)
    response = Response(
        {"access": str(refresh.access_token), "user": UserSerializer(user).data},
        status=status_code,
    )
    set_refresh_cookie(response, refresh)
    return response


class RegisterView(APIView):
    """POST /api/v1/auth/register (FR-1, FR-2, FR-7)."""

    permission_classes = [AllowAny]
    throttle_classes = [RegisterThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        token = make_email_verification_token(user.id)
        send_verification_email(to_email=user.email, token=token)

        logger.info("user_registered", extra={"user_id": str(user.id)})
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /api/v1/auth/login (FR-4, FR-7)."""

    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        # --- Track E --- FR-9: staff / enrolled users must present a TOTP code
        # before any JWT is issued (see accounts.twofactor for the contract).
        from accounts.twofactor import (
            requires_2fa_for_login,
            two_factor_challenge_response,
        )

        if requires_2fa_for_login(user):
            logger.info("user_login_2fa_challenged", extra={"user_id": str(user.id)})
            return two_factor_challenge_response(user)

        user.last_login_at = timezone.now()
        user.save(update_fields=["last_login_at", "updated_at"])

        logger.info("user_logged_in", extra={"user_id": str(user.id)})
        return _issue_tokens_response(user, request=request)


class RefreshView(APIView):
    """POST /api/v1/auth/refresh — reads the refresh token from the httpOnly
    cookie (FR-4). `TokenRefreshSerializer` + settings.SIMPLE_JWT's
    ROTATE_REFRESH_TOKENS/BLACKLIST_AFTER_ROTATION implement rotation with
    reuse detection: the old refresh jti is blacklisted and a new one issued.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        raw_refresh = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not raw_refresh:
            return Response({"detail": "Refresh token cookie is missing."}, status=401)

        serializer = TokenRefreshSerializer(data={"refresh": raw_refresh})
        # Raises InvalidToken (a DRF APIException, 401) on failure — handled by
        # the global RFC 7807 exception handler, no need to catch it here.
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        response = Response({"access": data["access"]}, status=200)
        set_refresh_cookie(response, data.get("refresh", raw_refresh))
        return response


class LogoutView(APIView):
    """POST /api/v1/auth/logout (FR-5) — blacklists the current refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw_refresh = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if raw_refresh:
            try:
                RefreshToken(raw_refresh).blacklist()
            except TokenError:
                pass  # already invalid/expired — logout is still a success from the client's view.

        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class VerifyEmailView(APIView):
    """POST /api/v1/auth/verify-email (FR-2)."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = read_email_verification_token(serializer.validated_data["token"])
        if not user_id:
            return Response(
                {"detail": "Invalid or expired verification token."}, status=400
            )

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "Invalid or expired verification token."}, status=400
            )

        if not user.is_email_verified:
            user.is_email_verified = True
            user.email_verified_at = timezone.now()
            user.save(
                update_fields=["is_email_verified", "email_verified_at", "updated_at"]
            )

        return Response({"detail": "Email verified."})


class PasswordResetRequestView(APIView):
    """POST /api/v1/auth/password/reset (FR-6, FR-7)."""

    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()

        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            token = make_password_reset_token(user)
            send_password_reset_email(to_email=user.email, token=token)

        # Always 202 regardless of whether the account exists — do not leak
        # account existence via response differences.
        return Response(status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(APIView):
    """POST /api/v1/auth/password/reset/confirm (FR-6)."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        parsed = read_password_reset_token(serializer.validated_data["token"])
        if not parsed:
            return Response({"detail": "Invalid or expired reset token."}, status=400)

        user_id, inner_token = parsed
        user = User.objects.filter(pk=user_id).first()
        if user is None or not password_reset_token_generator.check_token(
            user, inner_token
        ):
            return Response({"detail": "Invalid or expired reset token."}, status=400)

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        logger.info("password_reset_completed", extra={"user_id": str(user.id)})
        return Response({"detail": "Password updated."})


class GoogleAuthView(APIView):
    """POST /api/v1/auth/google (FR-3) — login/register via a verified Google
    ID token (openid email profile). Not the YouTube/AdSense data-access
    consent flow (see the `channels` app).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            claims = verify_google_id_token(serializer.validated_data["id_token"])
        except GoogleIDTokenError as exc:
            return Response({"detail": f"Invalid Google token: {exc}"}, status=400)

        google_sub = claims["sub"]
        email = claims.get("email", "").strip().lower()
        if not email:
            return Response({"detail": "Google account has no email."}, status=400)

        user = User.objects.filter(google_sub=google_sub).first()
        if user is None:
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "google_sub": google_sub,
                    "full_name": claims.get("name", ""),
                    "is_email_verified": bool(claims.get("email_verified", False)),
                    "email_verified_at": timezone.now()
                    if claims.get("email_verified")
                    else None,
                },
            )
            if not user.google_sub:
                user.google_sub = google_sub
                user.save(update_fields=["google_sub", "updated_at"])

        # --- Track E --- FR-9: Google sign-in is a first factor only for staff.
        from accounts.twofactor import (
            requires_2fa_for_login,
            two_factor_challenge_response,
        )

        if requires_2fa_for_login(user):
            logger.info("user_login_2fa_challenged", extra={"user_id": str(user.id)})
            return two_factor_challenge_response(user)

        user.last_login_at = timezone.now()
        user.save(update_fields=["last_login_at", "updated_at"])

        logger.info("user_logged_in_via_google", extra={"user_id": str(user.id)})
        return _issue_tokens_response(user, request=request)


class MeView(APIView):
    """GET/PATCH /api/v1/me."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = MeUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class PublicConfigurationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from django.conf import settings

        return Response({"google_client_id": settings.GOOGLE_OAUTH_CLIENT_ID})
