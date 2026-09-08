"""Stage 2 — script moderation gate (SPEC 7.1 #2; FR-45, FR-48, C-6).

OpenAI Moderation (`omni-moderation-latest` by default, model chosen in
`api_credentials_config`) scores the generated narration. Any category at or
above its threshold blocks the script.

Two policy decisions worth stating explicitly:

* **A blocked script is never auto-rejected.** FR-48 requires that content which
  fails moderation goes to a human moderator queue (`moderation_review`), with a
  `moderation_logs` row, and is never published automatically. Hard auto-reject
  is available behind `MODERATION_AUTO_REJECT_ON_BLOCK` but defaults to off.
* **The provider's own `flagged` boolean can only escalate, never de-escalate.**
  If OpenAI flags the text but every score sits under our thresholds, the verdict
  is still `flag` — we do not out-vote the provider downwards.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal

import requests
from django.conf import settings

from moderation.models import ModerationLog, ModerationStage, ModerationVerdict
from providers.exceptions import (
    ProviderAuthError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderRetryableError,
    ProviderTimeoutError,
)
from providers.models import ApiCredentialConfig, ServiceType
from providers.services import (
    compute_token_cost,
    get_primary_config,
    job_total_cost_usd,
    record_api_usage,
    resolve_api_key,
)

logger = logging.getLogger("video_pipeline.moderation")

OPERATION = "script_moderation"

DEFAULT_BLOCK_THRESHOLD = 0.5
DEFAULT_FLAG_THRESHOLD = 0.2


@dataclass
class ModerationOutcome:
    verdict: str
    max_category: str
    max_score: float
    category_scores: dict
    provider_flagged: bool
    thresholds: dict
    raw_response: dict = field(default_factory=dict)
    latency_ms: int | None = None
    http_status: int | None = None
    chunk_count: int = 0

    @property
    def is_blocking(self) -> bool:
        return self.verdict in (ModerationVerdict.FLAG, ModerationVerdict.BLOCK)


# ---------------------------------------------------------------------------
# Pure helpers (no DB, no network)
# ---------------------------------------------------------------------------
def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split on paragraph boundaries so a single sentence is never cut in half
    (a bisected sentence changes its own moderation score).
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        # A single paragraph longer than the limit is hard-split as a last resort.
        while len(paragraph) > max_chars:
            chunks.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def aggregate_category_scores(results: list[dict]) -> tuple[dict, bool]:
    """Worst-case merge across chunks: max score per category, OR of `flagged`."""
    scores: dict[str, float] = {}
    flagged = False
    for result in results or []:
        if not isinstance(result, dict):
            continue
        flagged = flagged or bool(result.get("flagged"))
        for category, value in (result.get("category_scores") or {}).items():
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            if score > scores.get(category, -1.0):
                scores[category] = score
    return scores, flagged


def evaluate_scores(
    category_scores: dict,
    *,
    provider_flagged: bool = False,
    block_threshold: float = DEFAULT_BLOCK_THRESHOLD,
    flag_threshold: float = DEFAULT_FLAG_THRESHOLD,
    category_thresholds: dict | None = None,
) -> tuple[str, str, float]:
    """Return `(verdict, worst_category, worst_score)`.

    `category_thresholds` lets an operator hold specific categories to a much
    lower bar (e.g. `sexual/minors: 0.05`) without lowering the global one.
    Severity is ranked by `score / threshold`, so a 0.4 score against a 0.05
    threshold outranks a 0.55 score against a 0.5 threshold.
    """
    category_thresholds = category_thresholds or {}

    blocked: list[tuple[str, float, float]] = []
    flagged: list[tuple[str, float, float]] = []
    worst_category, worst_score = "", 0.0

    for category, raw in (category_scores or {}).items():
        try:
            score = float(raw)
        except (TypeError, ValueError):
            continue
        if score > worst_score:
            worst_category, worst_score = category, score

        threshold = float(category_thresholds.get(category, block_threshold))
        if score >= threshold:
            blocked.append((category, score, threshold))
        elif score >= flag_threshold:
            flagged.append((category, score, flag_threshold))

    if blocked:
        category, score, _ = max(blocked, key=lambda item: item[1] / item[2] if item[2] else item[1])
        return ModerationVerdict.BLOCK, category, score
    if flagged:
        category, score, _ = max(flagged, key=lambda item: item[1])
        return ModerationVerdict.FLAG, category, score
    if provider_flagged:
        # Provider says flagged, our thresholds say clean -> escalate, never ignore.
        return ModerationVerdict.FLAG, worst_category, worst_score
    return ModerationVerdict.PASS, worst_category, worst_score


def resolve_thresholds(config: ApiCredentialConfig) -> dict:
    """Per-provider config overrides settings, settings override the defaults."""
    return {
        "block_threshold": float(
            config.get_option(
                "block_threshold", getattr(settings, "MODERATION_BLOCK_THRESHOLD", DEFAULT_BLOCK_THRESHOLD)
            )
        ),
        "flag_threshold": float(
            config.get_option(
                "flag_threshold", getattr(settings, "MODERATION_FLAG_THRESHOLD", DEFAULT_FLAG_THRESHOLD)
            )
        ),
        "category_thresholds": dict(config.get_option("category_thresholds", {}) or {}),
    }


# ---------------------------------------------------------------------------
# Provider client
# ---------------------------------------------------------------------------
class OpenAIModerationClient:
    """POST https://api.openai.com/v1/moderations — endpoint and model come from
    `api_credentials_config`, never from code.
    """

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
        self.base_url = config.get_option("base_url", settings.OPENAI_MODERATION_URL)
        self.model = config.model_name or "omni-moderation-latest"
        self.timeout = int(
            config.get_option("request_timeout_sec", getattr(settings, "MODERATION_TIMEOUT_SEC", 30))
        )

    def moderate(self, chunks: list[str]) -> tuple[dict, int, int]:
        """Return `(payload, latency_ms, http_status)` for a batch of text chunks."""
        if not chunks:
            raise ProviderPermanentError(
                "Nothing to moderate: the script text is empty.", error_code="moderation_empty_input"
            )

        started = time.monotonic()
        try:
            response = self._session.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "input": chunks},
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise ProviderTimeoutError(
                f"OpenAI Moderation request timed out after {self.timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderRetryableError("Could not reach the OpenAI Moderation API.") from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderRetryableError(
                f"OpenAI Moderation request failed: {type(exc).__name__}."
            ) from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        status = response.status_code
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                retry_after_sec = int(retry_after) if retry_after else None
            except (TypeError, ValueError):
                retry_after_sec = None
            raise ProviderRateLimitError(
                f"OpenAI Moderation returned HTTP {status}.", retry_after_sec=retry_after_sec
            )
        if status in (401, 403):
            raise ProviderAuthError(f"OpenAI Moderation returned HTTP {status}.", http_status=status)
        if status >= 500:
            raise ProviderRetryableError(
                f"OpenAI Moderation returned HTTP {status}.", http_status=status
            )
        if status >= 400:
            raise ProviderPermanentError(
                f"OpenAI Moderation returned HTTP {status}.", http_status=status
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("OpenAI Moderation returned a non-JSON body.") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ProviderResponseError("OpenAI Moderation response has no `results` array.")
        if not payload["results"]:
            raise ProviderResponseError("OpenAI Moderation returned an empty `results` array.")

        return payload, latency_ms, status


# ---------------------------------------------------------------------------
# DB-aware orchestration
# ---------------------------------------------------------------------------
def moderate_script_for_job(job, *, client=None) -> ModerationOutcome:
    """Run the FR-45 gate over `job.script_text` and persist a `moderation_logs` row.

    Returns the outcome; status transition is applied by `apply_verdict_to_job`
    so the caller (Celery task) keeps ownership of job state.
    """
    if not (job.script_text or "").strip():
        raise ProviderPermanentError(
            f"Video job {job.pk} has no script_text to moderate — run the script stage first.",
            error_code="moderation_empty_input",
        )

    config = get_primary_config(ServiceType.MODERATION)
    client = client or OpenAIModerationClient(config)

    max_chars = int(
        config.get_option(
            "max_chars_per_chunk", getattr(settings, "MODERATION_MAX_CHARS_PER_CHUNK", 8000)
        )
    )
    chunks = chunk_text(job.script_text, max_chars)

    try:
        payload, latency_ms, http_status = client.moderate(chunks)
    except Exception as exc:
        record_api_usage(
            config=config,
            operation=OPERATION,
            job=job,
            user=job.user,
            units=len(chunks),
            unit_type="requests",
            cost_usd=Decimal("0"),
            http_status=getattr(exc, "http_status", None),
            success=False,
            error_code=getattr(exc, "error_code", exc.__class__.__name__),
        )
        raise

    scores, provider_flagged = aggregate_category_scores(payload.get("results") or [])
    thresholds = resolve_thresholds(config)
    verdict, category, score = evaluate_scores(
        scores, provider_flagged=provider_flagged, **thresholds
    )

    cost = compute_token_cost(config, prompt_tokens=0, completion_tokens=0)
    record_api_usage(
        config=config,
        operation=OPERATION,
        job=job,
        user=job.user,
        units=len(chunks),
        unit_type="requests",
        cost_usd=cost,
        latency_ms=latency_ms,
        http_status=http_status,
        success=True,
        request_id=str(payload.get("id") or ""),
    )

    outcome = ModerationOutcome(
        verdict=verdict,
        max_category=category,
        max_score=score,
        category_scores=scores,
        provider_flagged=provider_flagged,
        thresholds=thresholds,
        raw_response=payload,
        latency_ms=latency_ms,
        http_status=http_status,
        chunk_count=len(chunks),
    )

    ModerationLog.objects.create(
        job=job,
        stage=ModerationStage.SCRIPT,
        provider=config.provider,
        verdict=verdict,
        categories=scores,
        threshold_config={
            **thresholds,
            "max_category": category,
            "max_score": score,
            "provider_flagged": provider_flagged,
        },
        raw_response=payload,
    )

    # Keep the job's running cost in sync even though moderation is currently free —
    # the number must stay correct if a paid moderation provider is swapped in.
    total_cost = job_total_cost_usd(job.pk)
    if job.total_cost_usd != total_cost:
        job.total_cost_usd = total_cost
        job.save(update_fields=["total_cost_usd", "updated_at"])

    logger.info(
        "script_moderation_completed",
        extra={
            "job_id": str(job.pk),
            "verdict": verdict,
            "max_category": category,
            "max_score": round(score, 4),
            "chunks": len(chunks),
        },
    )
    return outcome


def apply_verdict_to_job(job, outcome: ModerationOutcome) -> str:
    """Map a moderation verdict onto `video_jobs.status` (SPEC 7.2, FR-48).

    pass  -> `script_ready` (the stage-1 checkpoint; the voice stage picks up from here)
    flag  -> `moderation_review` (human queue, never auto-published)
    block -> `moderation_review`, or `moderation_rejected` when an operator has
             explicitly enabled `MODERATION_AUTO_REJECT_ON_BLOCK`.
    """
    from video_pipeline.models import JobStatus

    if outcome.verdict == ModerationVerdict.PASS:
        new_status = JobStatus.SCRIPT_READY
    elif (
        outcome.verdict == ModerationVerdict.BLOCK
        and getattr(settings, "MODERATION_AUTO_REJECT_ON_BLOCK", False)
    ):
        new_status = JobStatus.MODERATION_REJECTED
    else:
        new_status = JobStatus.MODERATION_REVIEW

    job.status = new_status
    update_fields = ["status", "updated_at"]

    if new_status != JobStatus.SCRIPT_READY:
        job.error_code = "script_moderation_flagged"
        job.error_message = (
            f"Script moderation verdict={outcome.verdict} "
            f"category={outcome.max_category or 'n/a'} score={round(outcome.max_score, 4)}."
        )
        update_fields += ["error_code", "error_message"]

    job.save(update_fields=update_fields)
    return new_status
