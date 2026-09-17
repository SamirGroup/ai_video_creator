"""Google "Sign in with Google" identity verification (FR-3).

This is a LOGIN identity check only (`openid email profile`) — entirely
separate from the YouTube/AdSense OAuth consent flows in the `channels` app,
which grant data-access scopes to an already-authenticated platform account.
No browser automation, no account creation on Google's side (C-1, C-2) — we
only verify a Google-issued ID token the frontend obtained via Google's own
Sign-In SDK.
"""

from __future__ import annotations

import logging

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

logger = logging.getLogger("accounts.google_oauth")


class GoogleIDTokenError(Exception):
    pass


def verify_google_id_token(raw_id_token: str) -> dict:
    """Verifies signature, issuer, expiry and audience. Returns the decoded claims
    (`sub`, `email`, `email_verified`, `name`, ...) or raises GoogleIDTokenError.
    """
    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        raise GoogleIDTokenError("Google sign-in is not configured.")
    try:
        claims = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            audience=settings.GOOGLE_OAUTH_CLIENT_ID,
        )
    except ValueError as exc:
        raise GoogleIDTokenError(str(exc)) from exc

    if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleIDTokenError("Unexpected token issuer.")
    if not claims.get("email_verified"):
        raise GoogleIDTokenError("Google email must be verified.")
    return claims
