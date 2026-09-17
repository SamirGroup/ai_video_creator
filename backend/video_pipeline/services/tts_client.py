"""ElevenLabs text-to-speech client (SPEC 7.1 #3, SPEC 9 "TTS", Q3 decision).

Endpoint, model id, voice defaults, output format and timeout all come from the
`api_credentials_config` row for `service="tts"` (FR-84) — nothing ElevenLabs-
specific beyond the URL shape is hardcoded.

    POST {base_url}/text-to-speech/{voice_id}?output_format=mp3_44100_128
    xi-api-key: <secret>            (never logged, never in the body)
    {"text": ..., "model_id": ..., "voice_settings": {...}}
    -> audio/mpeg bytes

Status mapping follows the project taxonomy (NFR-24): 429/5xx/timeouts are
retryable, everything else 4xx is permanent. Character counts are returned for
FR-51 per-character pricing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

from providers.exceptions import (
    ProviderAuthError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderRetryableError,
    ProviderTimeoutError,
)
from providers.models import ApiCredentialConfig
from providers.services import resolve_api_key

logger = logging.getLogger("video_pipeline.tts")

DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"


@dataclass(frozen=True)
class TTSResult:
    audio: bytes
    characters: int
    request_id: str
    latency_ms: int
    http_status: int
    content_type: str


def _retry_after(response) -> int | None:
    raw = response.headers.get("Retry-After")
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


class ElevenLabsClient:
    """Synchronous per-segment synthesis. One instance per stage invocation."""

    def __init__(
        self,
        config: ApiCredentialConfig,
        *,
        api_key: str | None = None,
        session: requests.Session | None = None,
    ):
        self.config = config
        self._api_key = api_key if api_key is not None else resolve_api_key(config)
        self._session = session or requests.Session()
        self.base_url = str(
            config.get_option(
                "base_url",
                getattr(
                    settings, "ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1"
                ),
            )
        ).rstrip("/")
        self.model_id = config.model_name or DEFAULT_MODEL_ID
        self.output_format = str(
            config.get_option("output_format", DEFAULT_OUTPUT_FORMAT)
        )
        self.timeout = int(
            config.get_option(
                "request_timeout_sec", getattr(settings, "VOICE_TTS_TIMEOUT_SEC", 120)
            )
        )
        self.default_voice_id = str(config.get_option("default_voice_id", "") or "")
        self.voice_settings = dict(config.get_option("voice_settings", {}) or {})
        self.max_chars_per_request = int(
            config.get_option("max_chars_per_request", 5000)
        )

    # -- public API ----------------------------------------------------------
    def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        language_code: str | None = None,
    ) -> TTSResult:
        text = (text or "").strip()
        if not text:
            raise ProviderPermanentError(
                "Cannot synthesize empty text.", error_code="tts_empty_input"
            )
        if len(text) > self.max_chars_per_request:
            raise ProviderPermanentError(
                f"Segment has {len(text)} characters; the provider limit is {self.max_chars_per_request}.",
                error_code="tts_segment_too_long",
            )
        voice = voice_id or self.default_voice_id
        if not voice:
            raise ProviderPermanentError(
                "No voice_id: set content_preferences.voice_id or `default_voice_id` in the TTS provider config.",
                error_code="tts_voice_not_configured",
            )

        payload: dict = {"text": text, "model_id": self.model_id}
        if self.voice_settings:
            payload["voice_settings"] = self.voice_settings
        if language_code and self.config.get_option("send_language_code", False):
            payload["language_code"] = self.config.get_option("language_codes", {}).get(
                language_code, language_code.split("-")[0]
            )

        url = f"{self.base_url}/text-to-speech/{voice}"
        started = time.monotonic()
        try:
            response = self._session.post(
                url,
                headers=self._headers(),
                params={"output_format": self.output_format},
                json=payload,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise ProviderTimeoutError(
                f"ElevenLabs request timed out after {self.timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderRetryableError(
                "Could not reach ElevenLabs (connection error)."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderRetryableError(
                f"ElevenLabs request failed: {type(exc).__name__}."
            ) from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        self._raise_for_status(response)

        audio = response.content or b""
        content_type = response.headers.get("Content-Type", "")
        if not audio or content_type.startswith("application/json"):
            raise ProviderResponseError("ElevenLabs returned no audio payload.")

        return TTSResult(
            audio=audio,
            characters=len(text),
            request_id=str(
                response.headers.get("request-id")
                or response.headers.get("x-request-id")
                or ""
            ),
            latency_ms=latency_ms,
            http_status=response.status_code,
            content_type=content_type or "audio/mpeg",
        )

    # -- internals -----------------------------------------------------------
    def _headers(self) -> dict:
        return {
            "xi-api-key": self._api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for_status(response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        detail = f"ElevenLabs returned HTTP {status}."
        if status == 429:
            raise ProviderRateLimitError(detail, retry_after_sec=_retry_after(response))
        if status == 408:
            raise ProviderTimeoutError(detail)
        if status in (401, 403):
            raise ProviderAuthError(detail, http_status=status)
        if status == 402:
            raise ProviderPermanentError(
                detail, error_code="provider_insufficient_credit", http_status=status
            )
        if status >= 500:
            raise ProviderRetryableError(detail, http_status=status)
        raise ProviderPermanentError(detail, http_status=status)
