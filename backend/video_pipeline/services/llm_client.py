"""OpenRouter chat-completions client (SPEC section 9, Q3: Claude via OpenRouter).

OpenRouter speaks the OpenAI `/chat/completions` shape, so this client stays
provider-shaped rather than model-shaped: the model id, base URL, temperature,
token cap and timeout all come from the `api_credentials_config` row that is
passed in — nothing about "Claude" is hardcoded here (FR-84).

Why `requests` and not an SDK: one endpoint, one payload shape, and we need
precise control over timeout + status-code -> retryable/permanent mapping
(NFR-24). An SDK would hide exactly the part we care about.

Security: the API key is only ever placed in the `Authorization` header. No
request body, no response body and no header dict is ever logged (NFR-3).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal

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

logger = logging.getLogger("video_pipeline.llm")


@dataclass(frozen=True)
class LLMResponse:
    """Everything the caller needs: the text, plus the numbers FR-51 wants."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    provider_cost_usd: Decimal | None
    request_id: str
    latency_ms: int
    http_status: int
    finish_reason: str


class OpenRouterClient:
    """Thin, synchronous OpenRouter client. One instance per stage invocation."""

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

        self.base_url = config.get_option("base_url", settings.OPENROUTER_BASE_URL)
        self.model = config.model_name
        if not self.model:
            raise ProviderPermanentError(
                "api_credentials_config row for service='llm' has an empty model_name.",
                error_code="provider_not_configured",
            )
        self.timeout = int(config.get_option("request_timeout_sec", settings.SCRIPT_LLM_TIMEOUT_SEC))

    # -- public API ----------------------------------------------------------
    def chat_completion(
        self,
        *,
        messages: list[dict],
        json_mode: bool | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": (
                temperature
                if temperature is not None
                else float(self.config.get_option("temperature", settings.SCRIPT_LLM_TEMPERATURE))
            ),
            "max_tokens": int(
                max_tokens
                if max_tokens is not None
                else self.config.get_option("max_output_tokens", settings.SCRIPT_LLM_MAX_OUTPUT_TOKENS)
            ),
        }

        use_json_mode = (
            json_mode if json_mode is not None else bool(self.config.get_option("json_mode", True))
        )
        if use_json_mode:
            # Structured output is enforced twice: here (provider-side JSON mode)
            # and in the parser, which never trusts the model to obey.
            payload["response_format"] = {"type": "json_object"}

        if self.config.get_option("include_usage_cost", True):
            # OpenRouter returns the real billed amount in `usage.cost`.
            payload["usage"] = {"include": True}

        started = time.monotonic()
        try:
            response = self._session.post(
                self.base_url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise ProviderTimeoutError(
                f"OpenRouter request timed out after {self.timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderRetryableError("Could not reach OpenRouter (connection error).") from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderRetryableError(f"OpenRouter request failed: {type(exc).__name__}.") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        self._raise_for_status(response)
        return self._parse(response, latency_ms=latency_ms)

    # -- internals -----------------------------------------------------------
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            # Optional OpenRouter attribution headers.
            "HTTP-Referer": getattr(settings, "OPENROUTER_APP_URL", "") or "",
            "X-Title": getattr(settings, "OPENROUTER_APP_TITLE", "") or "",
        }

    @staticmethod
    def _raise_for_status(response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return

        # Message text only — bodies can echo request content, so we keep it short
        # and never include headers (NFR-3).
        detail = f"OpenRouter returned HTTP {status}."

        if status == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                retry_after_sec = int(retry_after) if retry_after else None
            except (TypeError, ValueError):
                retry_after_sec = None
            raise ProviderRateLimitError(detail, retry_after_sec=retry_after_sec)
        if status == 408:
            raise ProviderTimeoutError(detail)
        if status in (401, 403):
            raise ProviderAuthError(detail, http_status=status)
        if status == 402:
            # Out of credit: retrying will not help, an operator must top up.
            raise ProviderPermanentError(detail, error_code="provider_insufficient_credit", http_status=status)
        if status >= 500:
            raise ProviderRetryableError(detail, http_status=status)
        raise ProviderPermanentError(detail, http_status=status)

    def _parse(self, response, *, latency_ms: int) -> LLMResponse:
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderResponseError("OpenRouter returned a non-JSON body.") from exc

        if not isinstance(data, dict):
            raise ProviderResponseError("OpenRouter returned an unexpected top-level JSON type.")

        # OpenRouter can answer 200 with an error envelope.
        if data.get("error"):
            code = str(data["error"].get("code", "")) if isinstance(data["error"], dict) else ""
            raise ProviderResponseError(f"OpenRouter returned an error envelope (code={code or 'unknown'}).")

        choices = data.get("choices") or []
        if not choices:
            raise ProviderResponseError("OpenRouter response contained no choices.")

        message = choices[0].get("message") or {}
        content = (message.get("content") or "").strip()
        finish_reason = choices[0].get("finish_reason") or ""
        if not content:
            raise ProviderResponseError(
                f"OpenRouter returned empty content (finish_reason={finish_reason or 'unknown'})."
            )

        usage = data.get("usage") or {}
        provider_cost = usage.get("cost")

        return LLMResponse(
            content=content,
            model=data.get("model") or self.model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(
                usage.get("total_tokens")
                or (int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0))
            ),
            provider_cost_usd=Decimal(str(provider_cost)) if provider_cost is not None else None,
            request_id=str(data.get("id") or response.headers.get("x-request-id") or ""),
            latency_ms=latency_ms,
            http_status=response.status_code,
            finish_reason=finish_reason,
        )


def get_llm_client(config, **kwargs):
    """Explicit routing: a direct Anthropic key is never sent to an intermediary."""
    if config.provider == "ollama":
        from video_pipeline.services.ollama_client import OllamaClient
        return OllamaClient(config, **kwargs)
    if config.provider == "anthropic":
        from video_pipeline.services.anthropic_client import AnthropicClient
        return AnthropicClient(config, **kwargs)
    if config.provider == "openrouter":
        return OpenRouterClient(config, **kwargs)
    raise ProviderPermanentError("Unsupported LLM provider.")
