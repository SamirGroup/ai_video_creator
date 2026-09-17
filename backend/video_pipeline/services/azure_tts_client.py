"""Azure Speech REST adapter; endpoint and locale/voice mapping are admin configuration."""

import time
from xml.etree.ElementTree import Element, SubElement, tostring

import requests

from providers.exceptions import (
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderRetryableError,
    ProviderTimeoutError,
)
from providers.services import resolve_api_key
from video_pipeline.services.tts_client import TTSResult


class AzureTTSClient:
    def __init__(self, config, *, api_key=None, session=None):
        self.config = config
        self.model_id = config.model_name
        self._api_key = api_key if api_key is not None else resolve_api_key(config)
        self._session = session or requests.Session()
        self.endpoint = str(config.get_option("endpoint", ""))
        if not self.endpoint.startswith("https://"):
            raise ProviderNotConfigured(
                "Azure TTS requires an HTTPS endpoint in provider configuration."
            )

    def synthesize(self, text, *, voice_id=None, language_code=None):
        locale = self.config.get_option("language_codes", {}).get(language_code)
        if not text.strip() or not voice_id or not locale:
            raise ProviderNotConfigured(
                "Azure TTS requires text, voice_id and a configured locale mapping."
            )
        if len(text) > int(self.config.get_option("max_chars_per_request", 5000)):
            raise ProviderPermanentError(
                "TTS segment exceeds the configured character limit."
            )
        root = Element(
            "speak",
            {
                "version": "1.0",
                "xmlns": "http://www.w3.org/2001/10/synthesis",
                "xml:lang": locale,
            },
        )
        SubElement(root, "voice", {"name": voice_id}).text = text
        started = time.monotonic()
        try:
            response = self._session.post(
                self.endpoint,
                data=tostring(root, encoding="utf-8"),
                headers={
                    "Ocp-Apim-Subscription-Key": self._api_key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                    "User-Agent": "AIYouTuber",
                },
                timeout=int(self.config.get_option("request_timeout_sec", 120)),
            )
        except requests.exceptions.Timeout as exc:
            raise ProviderTimeoutError("Azure TTS request timed out.") from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderRetryableError("Azure TTS connection failed.") from exc
        status = response.status_code
        if status in (401, 403):
            raise ProviderAuthError(
                "Azure TTS authorization failed.", http_status=status
            )
        if status == 429:
            raise ProviderRateLimitError("Azure TTS rate limit reached.")
        if status >= 500 or status == 408:
            raise ProviderRetryableError(
                "Azure TTS temporarily unavailable.", http_status=status
            )
        if not 200 <= status < 300:
            raise ProviderPermanentError(
                "Azure TTS rejected the request.", http_status=status
            )
        content_type = response.headers.get("Content-Type", "")
        if not response.content or not content_type.startswith("audio/"):
            raise ProviderResponseError("Azure TTS returned no audio payload.")
        return TTSResult(
            response.content,
            len(text),
            response.headers.get("X-RequestId", ""),
            int((time.monotonic() - started) * 1000),
            status,
            content_type,
        )
