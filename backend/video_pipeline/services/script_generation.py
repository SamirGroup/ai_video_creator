"""Stage 1 — script generation (SPEC 7.1 #1; FR-33, FR-34, FR-37, FR-43, FR-51, FR-52).

Flow:

    ContentPreference + last N titles
        -> prompt (video_pipeline.services.prompts)
        -> OpenRouter / Claude (video_pipeline.services.llm_client)
        -> defensive JSON parse + YouTube-limit normalisation (this module)
        -> FR-37 near-duplicate guard (one extra sample if the title collides)
        -> persist to video_jobs + video_assets checkpoint
        -> api_usage_logs row per call, job.total_cost_usd recomputed, FR-52 ceiling

The parsing/normalisation half of this module is deliberately free of Django
model access so it can be unit-tested without a database.
"""

from __future__ import annotations

from video_pipeline.services.stage_lock import serialized_paid_stage

from video_pipeline.services.preferences import job_preferences

import difflib
import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from providers.models import ServiceType
from providers.services import (
    compute_token_cost,
    get_primary_config,
    job_total_cost_usd,
    record_api_usage,
)
from video_pipeline.services import prompts
from video_pipeline.services.exceptions import (
    JobNotReady,
    ScriptParseError,
    ScriptValidationError,
)
from video_pipeline.services.llm_client import LLMResponse, get_llm_client

logger = logging.getLogger("video_pipeline.script")

OPERATION = "script_generation"

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass
class ScriptSegment:
    index: int
    heading: str
    narration: str
    visual_prompt: str
    target_duration_sec: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GeneratedScript:
    title: str
    description: str
    tags: list[str]
    segments: list[ScriptSegment]
    script_text: str
    estimated_duration_sec: int
    segment_duration_sum_sec: int
    word_count: int
    meta: dict = field(default_factory=dict)

    def segments_as_dicts(self) -> list[dict]:
        return [s.to_dict() for s in self.segments]


# ---------------------------------------------------------------------------
# Pure helpers (no DB) — unit-testable
# ---------------------------------------------------------------------------
def extract_json_object(content: str) -> dict:
    """Parse the model's answer into a dict, tolerating the usual deviations.

    Handles: clean JSON, ```json fenced blocks, and prose wrapped around a single
    JSON object. Never uses `eval`/`ast.literal_eval` — untrusted model output is
    only ever fed to `json.loads` (a strict, non-executing parser).
    """
    if not content or not content.strip():
        raise ScriptParseError("Model returned an empty response.")

    text = _JSON_FENCE_RE.sub("", content.strip()).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ScriptParseError("Model response contained no JSON object.") from None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ScriptParseError(
                f"Model response was not valid JSON ({exc.msg})."
            ) from None

    if not isinstance(parsed, dict):
        raise ScriptParseError(
            f"Model returned a JSON {type(parsed).__name__}, expected an object."
        )
    return parsed


def truncate_chars(value: str, limit: int) -> str:
    """Trim to `limit` characters, preferring the last word boundary."""
    value = _WS_RE.sub(" ", (value or "").strip())
    if len(value) <= limit:
        return value
    cut = value[:limit]
    space = cut.rfind(" ")
    if space >= limit * 0.6:  # only snap back to a word boundary if it isn't brutal
        cut = cut[:space]
    return cut.rstrip(" ,.;:-—")


def truncate_bytes(value: str, limit_bytes: int, encoding: str = "utf-8") -> str:
    """Trim so the UTF-8 encoding fits `limit_bytes` (SPEC 5.11: description is a
    *byte* limit, and non-ASCII scripts blow past it long before 5000 characters).
    """
    value = (value or "").strip()
    encoded = value.encode(encoding)
    if len(encoded) <= limit_bytes:
        return value
    trimmed = encoded[:limit_bytes].decode(encoding, errors="ignore")
    space = trimmed.rfind(" ")
    if space >= limit_bytes * 0.6:
        trimmed = trimmed[:space]
    return trimmed.rstrip()


def normalize_tags(
    raw_tags,
    *,
    max_total_chars: int = prompts.MAX_TAGS_TOTAL_CHARS,
    max_tag_chars: int = prompts.MAX_TAG_CHARS,
) -> list[str]:
    """Lowercase, de-duplicate and pack tags under YouTube's *combined* limit.

    YouTube counts the total length of all tags (500 chars). We budget
    `len(tag)` plus one separator per extra tag, and stop packing rather than
    letting the API reject the whole upload later.
    """
    if not isinstance(raw_tags, (list, tuple)):
        return []

    result: list[str] = []
    seen: set[str] = set()
    used = 0
    for item in raw_tags:
        if not isinstance(item, str):
            continue
        tag = _WS_RE.sub(" ", item.strip().lstrip("#").strip()).lower()
        if not tag:
            continue
        tag = tag[:max_tag_chars].strip()
        if not tag or tag in seen:
            continue
        addition = len(tag) + (1 if result else 0)
        if used + addition > max_total_chars:
            continue
        result.append(tag)
        seen.add(tag)
        used += addition
    return result


def normalize_title_for_comparison(title: str) -> str:
    text = unicodedata.normalize("NFKD", (title or "").lower())
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def max_title_similarity(title: str, recent_titles: list[str]) -> tuple[float, str]:
    """FR-37 near-duplicate guard.

    A lexical ratio, not an embedding. SPEC 5.11 reserves `topic_embedding` for a
    pgvector-based semantic check; that needs an embedding provider + pgvector
    which are not part of this stage. This catches the common failure mode (the
    model rewording a recent title) at zero cost and zero latency, and is a
    strict subset of what the semantic check will later do.
    """
    candidate = normalize_title_for_comparison(title)
    best_ratio = 0.0
    best_title = ""
    for existing in recent_titles or []:
        ratio = difflib.SequenceMatcher(
            None, candidate, normalize_title_for_comparison(existing)
        ).ratio()
        if ratio > best_ratio:
            best_ratio, best_title = ratio, existing
    return best_ratio, best_title


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _estimate_seconds_from_text(text: str) -> int:
    # CJK characters and Thai text do not require spaces between words.
    # This remains a planning estimate; measured TTS timing drives assembly.
    text = text or ""
    compact = re.findall(r"[\u3400-\u9fff\u3040-\u30ff\u0e00-\u0e7f]", text)
    spaced = re.sub(r"[\u3400-\u9fff\u3040-\u30ff\u0e00-\u0e7f]", " ", text)
    words = len(spaced.split())
    wpm = max(1, int(getattr(settings, "SCRIPT_WORDS_PER_MINUTE", 150)))
    return round(words / wpm * 60 + len(compact) / 5)


def normalize_script(payload: dict, *, target_duration_sec: int) -> GeneratedScript:
    """Turn a parsed model payload into a `GeneratedScript` that already satisfies
    every YouTube/DB limit, so nothing downstream has to re-check them.
    """
    title = truncate_chars(str(payload.get("title") or ""), prompts.MAX_TITLE_CHARS)
    if not title:
        raise ScriptValidationError("Model response is missing a title.")

    description = truncate_bytes(
        str(payload.get("description") or ""), prompts.MAX_DESCRIPTION_BYTES
    )
    tags = normalize_tags(payload.get("tags"))

    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ScriptValidationError("Model response contains no segments.")

    segments: list[ScriptSegment] = []
    for raw in raw_segments:
        if not isinstance(raw, dict):
            continue
        narration = _WS_RE.sub(" ", str(raw.get("narration") or "").strip())
        if not narration:
            continue
        index = len(segments) + 1  # renumber: the model's own indices are advisory
        duration = _coerce_int(raw.get("target_duration_sec"), 0)
        if duration <= 0:
            duration = max(1, _estimate_seconds_from_text(narration))
        segments.append(
            ScriptSegment(
                index=index,
                heading=truncate_chars(
                    str(raw.get("heading") or f"Segment {index}"), 80
                ),
                narration=narration,
                visual_prompt=truncate_chars(str(raw.get("visual_prompt") or ""), 400),
                target_duration_sec=duration,
            )
        )

    if not segments:
        raise ScriptValidationError(
            "Model response contained segments, but none had narration text."
        )

    script_text = "\n\n".join(s.narration for s in segments)
    word_count = len(script_text.split())
    segment_sum = sum(s.target_duration_sec for s in segments)
    # The word-count estimate predicts what TTS will actually produce, so it is
    # the number stored on the job; the model's own pacing plan is kept in meta
    # for the assembly stage.
    narration_estimate = _estimate_seconds_from_text(script_text)

    return GeneratedScript(
        title=title,
        description=description,
        tags=tags,
        segments=segments,
        script_text=script_text,
        estimated_duration_sec=max(1, narration_estimate),
        segment_duration_sum_sec=segment_sum,
        word_count=word_count,
        meta={
            "target_duration_sec": target_duration_sec,
            "segment_count": len(segments),
            "duration_deviation_pct": (
                round(
                    (narration_estimate - target_duration_sec)
                    / target_duration_sec
                    * 100,
                    1,
                )
                if target_duration_sec
                else None
            ),
        },
    )


def script_checksum(script: GeneratedScript) -> str:
    payload = json.dumps(
        {"title": script.title, "segments": script.segments_as_dicts()},
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# DB-aware orchestration
# ---------------------------------------------------------------------------
def collect_recent_topics(job, limit: int | None = None) -> list[str]:
    """FR-37: the last N titles produced for the same content preference
    (falling back to the same channel) as anti-repetition context.
    """
    from video_pipeline.models import VideoJob

    limit = limit or int(getattr(settings, "SCRIPT_RECENT_TOPICS_LIMIT", 20))
    qs = VideoJob.objects.exclude(pk=job.pk).exclude(title="")
    if job.preference_id:
        qs = qs.filter(preference_id=job.preference_id)
    else:
        qs = qs.filter(channel_id=job.channel_id)
    return list(qs.order_by("-created_at").values_list("title", flat=True)[:limit])


def _preference_of(job):
    preference = job_preferences(job)
    if preference is None:
        raise JobNotReady(
            f"Video job {job.pk} has no content_preferences row; the script stage "
            "cannot run without a niche, duration and language (FR-33)."
        )
    return preference


def _check_cost_ceiling(job, total_cost: Decimal) -> None:
    from video_pipeline.services.cost_control import check_cost_ceiling

    check_cost_ceiling(job, refresh=False)


def _call_llm_and_log(client, config, job, messages) -> LLMResponse:
    """One provider call + exactly one `api_usage_logs` row, success or failure."""
    from video_pipeline.services.cost_control import check_cost_ceiling

    from billing.wallet import reserve_job

    reserve_job(job)
    check_cost_ceiling(job)
    from billing.wallet import ensure_job_call_budget

    estimate = compute_token_cost(
        config,
        prompt_tokens=sum(len(str(m.get("content", "")).encode()) for m in messages),
        completion_tokens=int(config.get_option("max_output_tokens", 8000)),
    )
    ensure_job_call_budget(job, estimate)
    try:
        response = client.chat_completion(messages=messages)
    except Exception as exc:
        # A failed call still consumed latency, rate-limit budget and (on some
        # providers) tokens — FR-51/NFR-32 need it recorded, not swallowed.
        record_api_usage(
            config=config,
            operation=OPERATION,
            job=job,
            user=job.user,
            units=0,
            unit_type="tokens",
            cost_usd=Decimal("0"),
            latency_ms=None,
            http_status=getattr(exc, "http_status", None),
            success=False,
            error_code=getattr(exc, "error_code", exc.__class__.__name__),
        )
        raise

    cost = compute_token_cost(
        config,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        provider_reported_cost=response.provider_cost_usd,
    )
    record_api_usage(
        config=config,
        operation=OPERATION,
        job=job,
        user=job.user,
        units=response.total_tokens,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        unit_type="tokens",
        cost_usd=cost,
        latency_ms=response.latency_ms,
        http_status=response.http_status,
        success=True,
        request_id=response.request_id,
    )
    return response




@serialized_paid_stage
def generate_script_for_job(job, *, attempt: int = 1, client=None) -> GeneratedScript:
    """Generate, validate and persist the script for `job`.

    Idempotency (NFR-25): if the job already carries a script checkpoint
    (`script_text` + a `VideoAsset(kind=script)`), the LLM is not called again —
    an at-least-once redelivery of the Celery task must never double-charge.

    Raises `ProviderRetryableError` subclasses for transient provider problems
    (the task retries) and `ProviderPermanentError` subclasses otherwise.
    """
    from video_pipeline.models import AssetKind, VideoAsset

    existing = VideoAsset.objects.filter(job=job, kind=AssetKind.SCRIPT).first()
    if existing is not None and job.script_text:
        logger.info(
            "script_stage_skipped_checkpoint_exists",
            extra={"job_id": str(job.pk), "asset_id": str(existing.pk)},
        )
        return _script_from_checkpoint(job, existing)

    preference = _preference_of(job)
    config = get_primary_config(ServiceType.LLM)
    client = client or get_llm_client(config)

    duration_sec = int(preference.video_duration_sec or 180)
    language = job.language or preference.language or "en"
    recent_titles = collect_recent_topics(job)

    similarity_threshold = float(
        getattr(settings, "SCRIPT_TITLE_SIMILARITY_THRESHOLD", 0.9)
    )
    max_samples = max(1, int(getattr(settings, "SCRIPT_MAX_DEDUP_ATTEMPTS", 2)))

    regeneration_note = ""
    script: GeneratedScript | None = None
    response: LLMResponse | None = None
    fingerprint = ""
    similarity = 0.0
    similar_to = ""

    for sample in range(1, max_samples + 1):
        user_prompt = prompts.build_script_user_prompt(
            niche=preference.niche,
            custom_brief=preference.custom_brief
            + (
                "\nApproved content-plan topic and brief: "
                + json.dumps(job.generation_context, ensure_ascii=False)
                if job.generation_context
                else ""
            ),
            brand_voice=preference.brand_voice,
            banned_topics=list(preference.banned_topics or []),
            language=language,
            duration_sec=duration_sec,
            recent_titles=recent_titles,
            regeneration_note=regeneration_note,
        )
        messages = prompts.build_messages(prompts.SCRIPT_SYSTEM_PROMPT, user_prompt)
        fingerprint = prompts.prompt_fingerprint(messages)

        response = _call_llm_and_log(client, config, job, messages)
        script = normalize_script(
            extract_json_object(response.content), target_duration_sec=duration_sec
        )

        similarity, similar_to = max_title_similarity(script.title, recent_titles)
        if similarity < similarity_threshold or sample == max_samples:
            break

        logger.warning(
            "script_title_near_duplicate_resampling",
            extra={
                "job_id": str(job.pk),
                "similarity": round(similarity, 3),
                "sample": sample,
            },
        )
        regeneration_note = (
            f'Your previous attempt produced the title "{script.title}", which is a '
            f'near-duplicate of the already published title "{similar_to}". Choose a '
            "different subject entirely — not a rewording, not a narrower slice of the "
            "same subject."
        )

    assert script is not None and response is not None  # loop always runs at least once

    if similarity >= similarity_threshold:
        # Kept, not discarded: a flagged-but-usable script plus a visible warning
        # beats burning the whole job. The reviewer/moderator sees it in meta.
        logger.warning(
            "script_title_near_duplicate_accepted",
            extra={"job_id": str(job.pk), "similarity": round(similarity, 3)},
        )

    script.meta.update(
        {
            "provider": config.provider,
            "model": response.model,
            "prompt_sha256": fingerprint,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
            "finish_reason": response.finish_reason,
            "provider_request_id": response.request_id,
            "latency_ms": response.latency_ms,
            "recent_titles_considered": len(recent_titles),
            "title_similarity_max": round(similarity, 4),
            "title_similarity_threshold": similarity_threshold,
            "title_similarity_flagged": similarity >= similarity_threshold,
            "attempt": attempt,
            "language": language,
        }
    )

    _persist_script(job, script, config=config, response=response)
    # FR-52 is checked *after* the persist transaction commits on purpose: the
    # tokens are already spent, so the script must survive for the admin to
    # inspect. Raising here fails the job without discarding what it paid for.
    _check_cost_ceiling(job, job.total_cost_usd)
    return script


def _script_from_checkpoint(job, asset) -> GeneratedScript:
    """Rebuild the stage output from the stored checkpoint (FR-43) without a
    provider call, so a retry of a *later* stage never re-runs the LLM.
    """
    raw_segments = (asset.metadata or {}).get("segments") or []
    segments = [
        ScriptSegment(
            index=_coerce_int(s.get("index"), i + 1),
            heading=str(s.get("heading") or ""),
            narration=str(s.get("narration") or ""),
            visual_prompt=str(s.get("visual_prompt") or ""),
            target_duration_sec=_coerce_int(s.get("target_duration_sec"), 0),
        )
        for i, s in enumerate(raw_segments)
        if isinstance(s, dict)
    ]
    return GeneratedScript(
        title=job.title,
        description=job.description,
        tags=list(job.tags or []),
        segments=segments,
        script_text=job.script_text,
        estimated_duration_sec=int(job.duration_sec or 0),
        segment_duration_sum_sec=sum(s.target_duration_sec for s in segments),
        word_count=len(job.script_text.split()),
        meta=dict(job.script_meta or {}),
    )


@transaction.atomic
def _persist_script(job, script: GeneratedScript, *, config, response) -> None:
    """Write the stage result: job columns, the FR-43 checkpoint asset, and the
    recomputed FR-51 job cost (which also enforces the FR-52 ceiling).
    """
    from video_pipeline.models import AssetKind, VideoAsset

    checksum = script_checksum(script)
    payload = json.dumps(
        {
            "title": script.title,
            "description": script.description,
            "tags": script.tags,
            "segments": script.segments_as_dicts(),
        },
        ensure_ascii=False,
    )

    job.title = script.title
    job.description = script.description
    job.tags = script.tags
    job.script_text = script.script_text
    job.duration_sec = script.estimated_duration_sec
    job.language = script.meta.get("language") or job.language
    job.script_meta = {
        **(job.script_meta or {}),
        **script.meta,
        "checksum_sha256": checksum,
    }

    total_cost = job_total_cost_usd(job.pk)
    job.total_cost_usd = total_cost

    job.save(
        update_fields=[
            "title",
            "description",
            "tags",
            "script_text",
            "duration_sec",
            "language",
            "script_meta",
            "total_cost_usd",
            "updated_at",
        ]
    )

    # FR-43 checkpoint. The segments live in Postgres (not only S3) because the
    # voice stage consumes them directly; `s3_key` stays empty until the storage
    # layer lands, and `metadata.storage_state` records that honestly rather than
    # pointing at an object that does not exist.
    VideoAsset.objects.update_or_create(
        job=job,
        kind=AssetKind.SCRIPT,
        defaults={
            "s3_key": "",
            "mime_type": "application/json",
            "size_bytes": len(payload.encode("utf-8")),
            "duration_ms": script.estimated_duration_sec * 1000,
            "checksum_sha256": checksum,
            "provider": config.provider,
            "metadata": {
                "storage_state": "inline",
                "segments": script.segments_as_dicts(),
                "segment_duration_sum_sec": script.segment_duration_sum_sec,
                "word_count": script.word_count,
                "model": response.model,
            },
        },
    )
