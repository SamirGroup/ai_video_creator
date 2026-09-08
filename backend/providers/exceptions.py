"""Provider error taxonomy shared by every pipeline stage.

The split that matters operationally is **retryable vs permanent** (NFR-24, FR-44):

* `ProviderRetryableError` (429 / 5xx / timeout / connection reset) — the Celery
  task calls `self.retry()` with exponential backoff; the job goes to `retrying`,
  NOT `failed`. Quota is refunded only if all 3 attempts are exhausted.
* `ProviderPermanentError` (400 / 401 / 403 / 404 / 422, bad response shape) —
  retrying is pointless and only burns money/rate limit, so the task fails the
  job immediately with a precise `error_code`.

Never put response bodies that may echo the API key into these messages (NFR-3).
"""
from __future__ import annotations


class ProviderError(Exception):
    """Base class for every outbound-provider failure."""

    error_code = "provider_error"

    def __init__(self, message: str, *, error_code: str | None = None, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status
        if error_code:
            self.error_code = error_code


class ProviderRetryableError(ProviderError):
    """Transient — safe and worthwhile to retry with backoff."""

    error_code = "provider_unavailable"


class ProviderTimeoutError(ProviderRetryableError):
    error_code = "provider_timeout"


class ProviderRateLimitError(ProviderRetryableError):
    error_code = "provider_rate_limited"

    def __init__(self, message: str, *, retry_after_sec: int | None = None, http_status: int | None = 429):
        super().__init__(message, http_status=http_status)
        self.retry_after_sec = retry_after_sec


class ProviderPermanentError(ProviderError):
    """Deterministic failure — retrying the same request cannot help."""

    error_code = "provider_rejected_request"


class ProviderAuthError(ProviderPermanentError):
    error_code = "provider_auth_failed"


class ProviderResponseError(ProviderPermanentError):
    """Provider answered 2xx but the payload was not usable (shape/JSON/empty)."""

    error_code = "provider_bad_response"


class ProviderNotConfigured(ProviderPermanentError):
    """No active primary row in `api_credentials_config`, or its `secret_ref`
    resolves to nothing. This is an operator error, not a provider outage.
    """

    error_code = "provider_not_configured"
