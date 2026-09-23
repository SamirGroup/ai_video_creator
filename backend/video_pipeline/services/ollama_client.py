"""Private Ollama inference. The operator controls the endpoint, never a user prompt."""

import time
from decimal import Decimal
from urllib.parse import urlsplit

import requests
from django.conf import settings
from providers.exceptions import (
    ProviderNotConfigured,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderRetryableError,
    ProviderTimeoutError,
)

from video_pipeline.services.llm_client import LLMResponse


def endpoint():
    url = getattr(settings, "OLLAMA_BASE_URL", "").rstrip("/")
    parsed = urlsplit(url)
    if (
        not url
        or parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ProviderNotConfigured(
            "Configure OLLAMA_BASE_URL as a private Ollama origin."
        )
    return url


class OllamaClient:
    def __init__(self, config, *, session=None):
        self.config = config
        self.model = config.model_name
        self.base_url = endpoint()
        self.session = session or requests.Session()
        self.timeout = min(
            120, max(5, int(config.get_option("request_timeout_sec", 120)))
        )
        if not self.model or "cloud" in self.model.lower():
            raise ProviderNotConfigured(
                "Choose an installed local model, not a cloud model."
            )

    def chat_completion(
        self, *, messages, json_mode=None, max_tokens=None, temperature=None
    ):
        maximum = int(max_tokens or self.config.get_option("max_output_tokens", 4000))
        context = int(self.config.get_option("context_tokens", 8192))
        # Conservative bound: UTF-8 bytes upper-bound token usage; reject rather than silently drop tenant context.
        if sum(len(m["content"].encode()) + 32 for m in messages) + maximum > context:
            raise ProviderPermanentError(
                "Local model context capacity exceeded. Start a shorter conversation or increase capacity.",
                error_code="local_context_limit",
            )
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": "2m",
            "options": {
                "num_ctx": context,
                "num_predict": maximum,
                "temperature": temperature if temperature is not None else 0.4,
            },
        }
        if (
            json_mode
            if json_mode is not None
            else self.config.get_option("json_mode", True)
        ):
            payload["format"] = "json"
        headers = {"Content-Type": "application/json"}
        token = getattr(settings, "OLLAMA_API_KEY", "")
        if token:
            headers["Authorization"] = "Bearer " + token
        started = time.monotonic()
        try:
            response = self.session.post(
                self.base_url + "/api/chat",
                json=payload,
                headers=headers,
                timeout=(5, self.timeout),
                allow_redirects=False,
            )
        except requests.Timeout:
            raise ProviderTimeoutError("Local inference timed out.") from None
        except requests.RequestException:
            raise ProviderRetryableError("Local inference is unreachable.") from None
        if response.status_code in (429, 503):
            raise ProviderRateLimitError("Local inference is busy.")
        if response.status_code >= 500:
            raise ProviderRetryableError("Local inference failed.")
        if response.status_code != 200:
            raise ProviderPermanentError(
                "Local inference rejected the request.",
                http_status=response.status_code,
            )
        try:
            data = response.json()
            content = data["message"]["content"].strip()
            prompt = int(data["prompt_eval_count"])
            completion = int(data["eval_count"])
            if (
                not content
                or not data.get("done")
                or data.get("error")
                or min(prompt, completion) < 0
            ):
                raise ValueError()
            if data.get("done_reason") == "length":
                raise ProviderResponseError(
                    "Local model output was truncated; increase the output budget."
                )
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ProviderResponseError(
                "Local inference returned an invalid response."
            ) from None
        return LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            provider_cost_usd=Decimal(0),
            request_id="",
            latency_ms=int((time.monotonic() - started) * 1000),
            http_status=200,
            finish_reason=data.get("done_reason", "stop"),
        )
