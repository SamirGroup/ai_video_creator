"""Parsing + normalisation of the LLM script payload (no DB, no network).

These cover the failure modes that actually happen in production: fenced JSON,
prose around the object, YouTube limit overruns, and non-ASCII descriptions that
blow the *byte* limit long before the character limit.
"""
from __future__ import annotations

import json

import pytest

from video_pipeline.services import prompts
from video_pipeline.services.exceptions import ScriptParseError, ScriptValidationError
from video_pipeline.services.script_generation import (
    extract_json_object,
    max_title_similarity,
    normalize_script,
    normalize_tags,
    truncate_bytes,
    truncate_chars,
)
from video_pipeline.tests.fixtures import VALID_SCRIPT_PAYLOAD


class TestExtractJsonObject:
    def test_parses_clean_json(self):
        assert extract_json_object('{"title": "x"}') == {"title": "x"}

    def test_strips_markdown_fences(self):
        raw = '```json\n{"title": "x", "n": 1}\n```'
        assert extract_json_object(raw) == {"title": "x", "n": 1}

    def test_recovers_object_wrapped_in_prose(self):
        raw = 'Sure! Here is the script:\n{"title": "x"}\nLet me know if you want changes.'
        assert extract_json_object(raw) == {"title": "x"}

    def test_empty_response_raises(self):
        with pytest.raises(ScriptParseError):
            extract_json_object("   ")

    def test_non_json_raises(self):
        with pytest.raises(ScriptParseError):
            extract_json_object("I cannot help with that request.")

    def test_json_array_is_rejected(self):
        with pytest.raises(ScriptParseError):
            extract_json_object('[{"title": "x"}]')

    def test_broken_json_raises_rather_than_returning_partial(self):
        with pytest.raises(ScriptParseError):
            extract_json_object('{"title": "x", "segments": [')


class TestTruncation:
    def test_title_is_capped_at_youtube_limit(self):
        long_title = "word " * 60
        assert len(truncate_chars(long_title, prompts.MAX_TITLE_CHARS)) <= prompts.MAX_TITLE_CHARS

    def test_short_title_is_untouched(self):
        assert truncate_chars("A tight title", 100) == "A tight title"

    def test_description_respects_byte_limit_for_multibyte_text(self):
        # Cyrillic: 2 bytes per character, so 3000 chars is ~6000 bytes.
        text = "тест " * 600
        result = truncate_bytes(text, prompts.MAX_DESCRIPTION_BYTES)
        assert len(result.encode("utf-8")) <= prompts.MAX_DESCRIPTION_BYTES
        assert len(result) < len(text)

    def test_truncation_never_produces_invalid_utf8(self):
        result = truncate_bytes("é" * 100, 15)
        result.encode("utf-8").decode("utf-8")  # must not raise
        assert len(result.encode("utf-8")) <= 15


class TestNormalizeTags:
    def test_lowercases_strips_hashes_and_dedupes(self):
        assert normalize_tags([" Travel ", "#travel", "TRAVEL", "cider"]) == ["travel", "cider"]

    def test_total_length_stays_under_500_chars(self):
        tags = [f"{'tag' * 8}{i}" for i in range(60)]
        result = normalize_tags(tags)
        total = sum(len(t) for t in result) + max(0, len(result) - 1)
        assert total <= prompts.MAX_TAGS_TOTAL_CHARS

    def test_individual_tag_is_capped_to_model_field_width(self):
        result = normalize_tags(["x" * 200])
        assert len(result[0]) <= prompts.MAX_TAG_CHARS

    def test_non_list_input_returns_empty(self):
        assert normalize_tags("travel, cider") == []
        assert normalize_tags(None) == []


class TestNormalizeScript:
    def test_happy_path(self):
        script = normalize_script(VALID_SCRIPT_PAYLOAD, target_duration_sec=60)
        assert script.title == VALID_SCRIPT_PAYLOAD["title"]
        assert len(script.segments) == 3
        assert script.segments[0].index == 1
        assert script.segment_duration_sum_sec == 60
        # script_text is what TTS and the moderation gate consume.
        assert script.script_text.count("\n\n") == 2
        assert script.word_count > 0
        assert script.estimated_duration_sec > 0

    def test_segments_are_renumbered_consecutively(self):
        payload = json.loads(json.dumps(VALID_SCRIPT_PAYLOAD))
        payload["segments"][0]["index"] = 7
        payload["segments"][2]["index"] = 99
        script = normalize_script(payload, target_duration_sec=60)
        assert [s.index for s in script.segments] == [1, 2, 3]

    def test_segments_without_narration_are_dropped(self):
        payload = json.loads(json.dumps(VALID_SCRIPT_PAYLOAD))
        payload["segments"].append({"index": 4, "heading": "empty", "narration": "   "})
        script = normalize_script(payload, target_duration_sec=60)
        assert len(script.segments) == 3

    def test_missing_duration_is_estimated_from_word_count(self):
        payload = json.loads(json.dumps(VALID_SCRIPT_PAYLOAD))
        for segment in payload["segments"]:
            segment.pop("target_duration_sec")
        script = normalize_script(payload, target_duration_sec=60)
        assert all(s.target_duration_sec > 0 for s in script.segments)

    def test_missing_title_is_rejected(self):
        payload = json.loads(json.dumps(VALID_SCRIPT_PAYLOAD))
        payload["title"] = ""
        with pytest.raises(ScriptValidationError):
            normalize_script(payload, target_duration_sec=60)

    def test_missing_segments_is_rejected(self):
        payload = json.loads(json.dumps(VALID_SCRIPT_PAYLOAD))
        payload["segments"] = []
        with pytest.raises(ScriptValidationError):
            normalize_script(payload, target_duration_sec=60)

    def test_all_segments_empty_is_rejected(self):
        payload = json.loads(json.dumps(VALID_SCRIPT_PAYLOAD))
        payload["segments"] = [{"index": 1, "narration": ""}]
        with pytest.raises(ScriptValidationError):
            normalize_script(payload, target_duration_sec=60)

    def test_overlong_fields_are_clamped_to_db_and_api_limits(self):
        payload = json.loads(json.dumps(VALID_SCRIPT_PAYLOAD))
        payload["title"] = "T" * 400
        payload["description"] = "D" * 20000
        payload["tags"] = [f"tag-number-{i}" for i in range(200)]
        script = normalize_script(payload, target_duration_sec=60)
        assert len(script.title) <= prompts.MAX_TITLE_CHARS
        assert len(script.description.encode("utf-8")) <= prompts.MAX_DESCRIPTION_BYTES
        assert sum(len(t) for t in script.tags) + len(script.tags) - 1 <= prompts.MAX_TAGS_TOTAL_CHARS


class TestTitleSimilarity:
    """FR-37 near-duplicate guard."""

    def test_identical_titles_score_one(self):
        ratio, match = max_title_similarity("Five Ways To Brew Coffee", ["Five ways to brew coffee!"])
        assert ratio == pytest.approx(1.0)
        assert match == "Five ways to brew coffee!"

    def test_reworded_title_scores_high(self):
        ratio, _ = max_title_similarity(
            "How To Brew Better Coffee At Home", ["How to Brew Better Coffee at Home?"]
        )
        assert ratio > 0.9

    def test_unrelated_title_scores_low(self):
        ratio, _ = max_title_similarity(
            "Why Basque Cider Is Poured From Above", ["Rebuilding a 1970s motorcycle carburettor"]
        )
        assert ratio < 0.6

    def test_empty_history_scores_zero(self):
        assert max_title_similarity("anything", []) == (0.0, "")


class TestPromptConstruction:
    """FR-34 / FR-37 / C-6: the constraints must physically be in the prompt."""

    def test_banned_topics_and_brand_voice_reach_the_prompt(self):
        prompt = prompts.build_script_user_prompt(
            niche="cooking",
            brand_voice="Dry, precise, no hype. Audience: home cooks who already know the basics.",
            banned_topics=["politics", "alcohol"],
            language="en",
            duration_sec=180,
        )
        assert "BANNED TOPICS" in prompt
        assert "politics" in prompt and "alcohol" in prompt
        assert "Dry, precise, no hype" in prompt

    def test_recent_titles_are_injected_as_an_avoid_list(self):
        prompt = prompts.build_script_user_prompt(
            niche="travel", duration_sec=120, recent_titles=["A Weekend In Bilbao"]
        )
        assert "ALREADY PUBLISHED" in prompt
        assert "A Weekend In Bilbao" in prompt

    def test_absent_optional_fields_leave_no_empty_sections(self):
        prompt = prompts.build_script_user_prompt(niche="tech", duration_sec=90)
        assert "BANNED TOPICS" not in prompt
        assert "BRAND VOICE" not in prompt
        assert "ALREADY PUBLISHED" not in prompt

    def test_system_prompt_forbids_mass_produced_content(self):
        # C-6 / Risk R-2: YouTube's inauthentic-content policy is the reason
        # this instruction exists; losing it silently would be a policy risk.
        system = prompts.SCRIPT_SYSTEM_PROMPT
        assert "ORIGINALITY" in system
        assert "mass-produced" in system
        assert "In today's video" in system  # the forbidden generic opener

    def test_fingerprint_is_stable_and_prompt_sensitive(self):
        a = prompts.build_messages("sys", "user")
        b = prompts.build_messages("sys", "user")
        c = prompts.build_messages("sys", "user 2")
        assert prompts.prompt_fingerprint(a) == prompts.prompt_fingerprint(b)
        assert prompts.prompt_fingerprint(a) != prompts.prompt_fingerprint(c)

    def test_segment_count_scales_with_duration_and_is_clamped(self):
        assert prompts.target_segment_count(30) == prompts.MIN_SEGMENTS
        assert prompts.target_segment_count(600) > prompts.MIN_SEGMENTS
        assert prompts.target_segment_count(100000) == prompts.MAX_SEGMENTS
