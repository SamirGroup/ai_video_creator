"""Direct Anthropic Messages API; no OpenRouter routing or secret-bearing URLs."""

import time
from decimal import Decimal

import requests
from providers.exceptions import (
    ProviderAuthError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderRetryableError,
    ProviderTimeoutError,
)
from providers.services import resolve_api_key

from video_pipeline.services.llm_client import LLMResponse


class AnthropicClient:
    base_url = "https://api.anthropic.com/v1"

    def __init__(self, config, *, api_key=None, session=None):
        self.config = config
        self.model = config.model_name
        self._api_key = api_key if api_key is not None else resolve_api_key(config)
        self._session = session or requests.Session()
        self.timeout = min(
            120, max(5, int(config.get_option("request_timeout_sec", 90)))
        )
        if not self.model:
            raise ProviderPermanentError("Anthropic model is not configured.")

    def _request(self, method, path, **kwargs):
        try:
            response = self._session.request(
                method,
                self.base_url + path,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
                allow_redirects=False,
                **kwargs,
            )
        except requests.Timeout:
            raise ProviderTimeoutError("Anthropic request timed out.") from None
        except requests.RequestException:
            raise ProviderRetryableError("Anthropic connection failed.") from None
        status = response.status_code
        if status in (401, 403):
            raise ProviderAuthError(
                "Anthropic authentication failed.", http_status=status
            )
        if status == 429:
            raise ProviderRateLimitError("Anthropic rate limit reached.")
        if status >= 500:
            raise ProviderRetryableError(
                "Anthropic is temporarily unavailable.", http_status=status
            )
        if not 200 <= status < 300:
            raise ProviderPermanentError(
                f"Anthropic returned HTTP {status}.", http_status=status
            )
        try:
            data = response.json()
        except ValueError:
            raise ProviderResponseError("Anthropic returned invalid JSON.") from None
        if not isinstance(data, dict) or data.get("type") == "error":
            raise ProviderResponseError("Anthropic returned an invalid response.")
        return data, response

    def check_model(self):
        from urllib.parse import quote

        data, _ = self._request("GET", "/models/" + quote(self.model, safe=""))
        if not data.get("id") or data.get("type") != "model":
            raise ProviderResponseError("Anthropic model is unavailable.")
        return data["id"]

    def chat_completion(
        self, *, messages, json_mode=None, max_tokens=None, temperature=None
    ):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        conversation = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]
        if not conversation:
            raise ProviderPermanentError("At least one user message is required.")
        if (
            json_mode
            if json_mode is not None
            else self.config.get_option("json_mode", True)
        ):
            system += "\nReturn only valid JSON matching the requested structure, with no markdown fences."
        payload = {
            "model": self.model,
            "max_tokens": int(
                max_tokens or self.config.get_option("max_output_tokens", 4000)
            ),
            "messages": conversation,
        }
        if system:
            payload["system"] = system
        # No temperature or thinking overrides: capabilities differ by Claude model.
        started = time.monotonic()
        data, response = self._request("POST", "/messages", json=payload)
        try:
            content = "\n".join(
                block["text"]
                for block in data.get("content", [])
                if block.get("type") == "text"
            ).strip()
            usage = data["usage"]
            normal = int(usage["input_tokens"])
            output = int(usage["output_tokens"])
            cached = int(usage.get("cache_read_input_tokens", 0))
            written = int(usage.get("cache_creation_input_tokens", 0))
            if min(normal, output, cached, written) < 0:
                raise ValueError()
            input_rate = Decimal(str(self.config.get_option("input_cost_per_1k_usd")))
            output_rate = Decimal(str(self.config.get_option("output_cost_per_1k_usd")))
            cost = (
                Decimal(normal) * input_rate
                + Decimal(output) * output_rate
                + Decimal(cached) * input_rate * Decimal(".1")
                + Decimal(written) * input_rate * Decimal("1.25")
            ) / 1000
        except (KeyError, ValueError, TypeError, ArithmeticError):
            raise ProviderResponseError(
                "Anthropic usage or pricing is invalid."
            ) from None
        if not content:
            raise ProviderResponseError("Anthropic returned no text.")
        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            prompt_tokens=normal + cached + written,
            completion_tokens=output,
            total_tokens=normal + cached + written + output,
            provider_cost_usd=cost,
            request_id=str(data.get("id") or response.headers.get("request-id", "")),
            latency_ms=int((time.monotonic() - started) * 1000),
            http_status=response.status_code,
            finish_reason=data.get("stop_reason", ""),
        )
