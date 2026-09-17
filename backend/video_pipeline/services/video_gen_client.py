"""Runway video-generation client (SPEC 7.1 #4, SPEC 9 "Video generation", Q3).

Runway's API is asynchronous: create a task, poll `GET /tasks/{id}` until it is
`SUCCEEDED` (output URLs) or `FAILED`, then download the MP4. Model id, base
URL, API version header, allowed clip durations and ratio mapping all come from
the `api_credentials_config` row for `service="video_gen"` (FR-84).

    POST {base_url}/{create_path}      create_path: text_to_video (default) | image_to_video
      {"model": ..., "promptText": ..., "duration": 5|10, "ratio": "1280:720"[, "promptImage": url]}
    GET  {base_url}/tasks/{id}          -> {"status": PENDING|RUNNING|SUCCEEDED|FAILED|CANCELLED,
                                            "output": [url], "failure": ..., "failureCode": ...}

Polling uses a capped exponential backoff and a hard wall-clock budget
(`task_timeout_sec`); exceeding it raises `ProviderTimeoutError` (retryable —
the stage re-polls the same task id on retry instead of paying twice).
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

logger = logging.getLogger("video_pipeline.video_gen")

DEFAULT_API_VERSION = "2024-11-06"
DEFAULT_ALLOWED_DURATIONS = (5, 10)
DEFAULT_RATIO_MAP = {"16:9": "1280:720", "9:16": "720:1280", "1:1": "960:960"}
TERMINAL_SUCCESS = "SUCCEEDED"
TERMINAL_FAILURE = {"FAILED", "CANCELLED", "CANCELED"}


@dataclass(frozen=True)
class VideoTask:
    task_id: str
    duration_sec: int
    ratio: str
    request_id: str = ""
    latency_ms: int = 0
    http_status: int = 0


@dataclass(frozen=True)
class VideoTaskResult:
    task_id: str
    status: str
    output_urls: tuple[str, ...]
    raw: dict
    polls: int


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def pick_clip_duration(
    target_sec: float, allowed: tuple[int, ...] | list[int] = DEFAULT_ALLOWED_DURATIONS
) -> int:
    """Smallest allowed clip length that covers `target_sec`, else the longest
    (assembly loops/trims to the exact segment length, FR-50).
    """
    options = sorted({int(d) for d in allowed if int(d) > 0}) or list(
        DEFAULT_ALLOWED_DURATIONS
    )
    for option in options:
        if option >= target_sec:
            return option
    return options[-1]


def ratio_for_aspect(aspect_ratio: str, ratio_map: dict | None = None) -> str:
    mapping = {**DEFAULT_RATIO_MAP, **(ratio_map or {})}
    return mapping.get(aspect_ratio or "16:9", mapping["16:9"])


def poll_delay(attempt: int, *, base_sec: float, max_sec: float) -> float:
    return min(max_sec, base_sec * (1.5 ** max(0, attempt)))


def _retry_after(response) -> int | None:
    raw = response.headers.get("Retry-After")
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


class RunwayClient:
    def __init__(
        self,
        config: ApiCredentialConfig,
        *,
        api_key: str | None = None,
        session: requests.Session | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.config = config
        self._api_key = api_key if api_key is not None else resolve_api_key(config)
        self._session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock

        self.base_url = str(
            config.get_option(
                "base_url",
                getattr(settings, "RUNWAY_BASE_URL", "https://api.dev.runwayml.com/v1"),
            )
        ).rstrip("/")
        self.model = config.model_name
        if not self.model:
            raise ProviderPermanentError(
                "api_credentials_config row for service='video_gen' has an empty model_name.",
                error_code="provider_not_configured",
            )
        self.api_version = str(
            config.get_option(
                "api_version",
                getattr(settings, "RUNWAY_API_VERSION", DEFAULT_API_VERSION),
            )
        )
        self.create_path = str(config.get_option("create_path", "text_to_video")).strip(
            "/"
        )
        self.request_timeout = int(config.get_option("request_timeout_sec", 60))
        self.task_timeout = int(
            config.get_option(
                "task_timeout_sec", getattr(settings, "VISUAL_TASK_TIMEOUT_SEC", 900)
            )
        )
        self.poll_base = float(
            config.get_option(
                "poll_interval_sec", getattr(settings, "VISUAL_POLL_INTERVAL_SEC", 5)
            )
        )
        self.poll_max = float(config.get_option("poll_max_interval_sec", 30))
        self.allowed_durations = tuple(
            int(d)
            for d in config.get_option("allowed_durations", DEFAULT_ALLOWED_DURATIONS)
        )
        self.ratio_map = dict(config.get_option("ratio_map", {}) or {})
        self.download_timeout = int(config.get_option("download_timeout_sec", 300))

    # -- public API ----------------------------------------------------------
    def create_task(
        self,
        *,
        prompt: str,
        target_duration_sec: float,
        aspect_ratio: str = "16:9",
        image_url: str | None = None,
        seed: int | None = None,
    ) -> VideoTask:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ProviderPermanentError(
                "Cannot create a video task with an empty prompt.",
                error_code="visual_empty_prompt",
            )

        duration = pick_clip_duration(target_duration_sec, self.allowed_durations)
        ratio = ratio_for_aspect(aspect_ratio, self.ratio_map)
        payload: dict = {
            "model": self.model,
            "promptText": prompt,
            "duration": duration,
            "ratio": ratio,
        }
        payload.update(self.config.get_option("request_options", {}))
        if image_url:
            payload["promptImage"] = image_url
        if seed is not None:
            payload["seed"] = int(seed)

        started = self._clock()
        response = self._request(
            "POST", f"{self.base_url}/{self.create_path}", json=payload
        )
        latency_ms = int((self._clock() - started) * 1000)
        data = self._json(response)
        task_id = str(data.get("id") or "")
        if not task_id:
            raise ProviderResponseError("Runway task creation returned no task id.")
        return VideoTask(
            task_id=task_id,
            duration_sec=duration,
            ratio=ratio,
            request_id=str(response.headers.get("x-request-id") or task_id),
            latency_ms=latency_ms,
            http_status=response.status_code,
        )

    def get_task(self, task_id: str) -> dict:
        return self._json(self._request("GET", f"{self.base_url}/tasks/{task_id}"))

    def wait_for_task(
        self, task_id: str, *, timeout_sec: int | None = None
    ) -> VideoTaskResult:
        budget = timeout_sec if timeout_sec is not None else self.task_timeout
        deadline = self._clock() + budget
        attempt = 0
        while True:
            data = self.get_task(task_id)
            status = str(data.get("status") or "").upper()
            attempt += 1
            if status == TERMINAL_SUCCESS:
                outputs = tuple(str(u) for u in (data.get("output") or []) if u)
                if not outputs:
                    raise ProviderResponseError(
                        f"Runway task {task_id} succeeded without output URLs."
                    )
                return VideoTaskResult(
                    task_id=task_id,
                    status=status,
                    output_urls=outputs,
                    raw=data,
                    polls=attempt,
                )
            if status in TERMINAL_FAILURE:
                code = str(data.get("failureCode") or "")
                # Runway's own retryable hints ("INTERNAL", throttling) are worth one more attempt.
                if code.upper().startswith("INTERNAL") or "THROTTL" in code.upper():
                    raise ProviderRetryableError(
                        f"Runway task {task_id} failed with a transient code ({code}).",
                        error_code="visual_task_failed_transient",
                    )
                raise ProviderPermanentError(
                    f"Runway task {task_id} failed ({code or status}).",
                    error_code="visual_task_failed",
                )
            if self._clock() >= deadline:
                raise ProviderTimeoutError(
                    f"Runway task {task_id} did not finish within {budget}s (last status={status or 'unknown'})."
                )
            self._sleep(
                poll_delay(attempt - 1, base_sec=self.poll_base, max_sec=self.poll_max)
            )

    def download(self, url: str) -> bytes:
        try:
            response = self._session.get(
                url, timeout=self.download_timeout, stream=True
            )
        except requests.exceptions.Timeout as exc:
            raise ProviderTimeoutError(
                "Downloading the generated clip timed out."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderRetryableError(
                f"Downloading the generated clip failed: {type(exc).__name__}."
            ) from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise ProviderRetryableError(
                f"Clip download returned HTTP {response.status_code}.",
                http_status=response.status_code,
            )
        if response.status_code >= 400:
            # Output URLs are short-lived; an expired URL means the task must be re-created.
            raise ProviderRetryableError(
                f"Clip download returned HTTP {response.status_code}.",
                error_code="visual_output_expired",
                http_status=response.status_code,
            )
        data = response.content
        if not data:
            raise ProviderResponseError("Downloaded clip is empty.")
        return data

    # -- internals -----------------------------------------------------------
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "X-Runway-Version": self.api_version,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, url: str, *, json: dict | None = None):
        try:
            response = self._session.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                timeout=self.request_timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise ProviderTimeoutError(
                f"Runway request timed out after {self.request_timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderRetryableError(
                "Could not reach Runway (connection error)."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderRetryableError(
                f"Runway request failed: {type(exc).__name__}."
            ) from exc
        self._raise_for_status(response)
        return response

    @staticmethod
    def _raise_for_status(response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        detail = f"Runway returned HTTP {status}."
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

    @staticmethod
    def _json(response) -> dict:
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderResponseError("Runway returned a non-JSON body.") from exc
        if not isinstance(data, dict):
            raise ProviderResponseError(
                "Runway returned an unexpected top-level JSON type."
            )
        return data
