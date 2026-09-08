"""Prompt construction for the script stage (FR-33, FR-34, FR-37, C-6, Risk R-2).

Three things this file is responsible for, and they are worth stating because
they are the difference between a usable product and a policy strike:

1. **Originality (C-6 / R-2).** YouTube's "inauthentic content" policy demonetises
   mass-produced, templated, low-effort uploads. The system prompt therefore
   forbids the generic-AI-video shape explicitly (listicle-of-obvious-facts,
   stock motivational filler, "in today's video we will explore..." openers) and
   demands a specific angle with concrete, checkable detail.
2. **Brand voice and hard bans (FR-34).** The creator's `brand_voice` is applied
   as tone instruction; `banned_topics` is a hard constraint repeated in both the
   system and user message, because a single mention is easy for a model to lose
   in a long context.
3. **Non-repetition (FR-37).** The last N titles are injected as an explicit
   avoid-list. A lexical similarity guard in `script_generation` catches the
   cases where the model ignores it.

The output contract is a single JSON object. It is stated once, precisely, with
no examples that the model could copy verbatim into the actual script.
"""
from __future__ import annotations

import hashlib
import json

# Roughly one visual/narration beat every ~18 seconds; clamped to sane bounds.
SECONDS_PER_SEGMENT = 18
MIN_SEGMENTS = 3
MAX_SEGMENTS = 30

# Hard platform limits mirrored from SPEC 5.11 / YouTube Data API.
MAX_TITLE_CHARS = 100
MAX_DESCRIPTION_BYTES = 5000
MAX_TAGS_TOTAL_CHARS = 500
MAX_TAG_CHARS = 64

SCRIPT_SYSTEM_PROMPT = """\
You are a senior YouTube writer-producer. You write scripts that a real human \
expert would be willing to put their own name on.

NON-NEGOTIABLE RULES

1. ORIGINALITY. The video must be worth a viewer's time on its own merits. It \
must have one specific angle, not a broad survey of a topic. Include concrete, \
verifiable specifics: named examples, numbers, mechanisms, trade-offs, or a \
first-hand-style walkthrough. Generic, interchangeable, mass-produced content is \
a failure condition, not a stylistic preference.

2. FORBIDDEN SHAPES. Do not write: filler openers such as "In today's video we \
will explore..."; "Top N facts you won't believe" listicles of common knowledge; \
vague motivational padding; padded restatements of the title; sentences that \
could appear unchanged in a video about any other topic.

3. FACTUAL DISCIPLINE. Never invent statistics, studies, quotes, prices, dates \
or events. If a precise figure is not something you are confident about, describe \
the relationship qualitatively instead. No medical, legal or financial advice \
framed as instruction.

4. RIGHTS AND SAFETY. No copyrighted lyrics, no quoted song text, no scripted \
impersonation of a real identifiable person, no defamatory claims, no hate, \
harassment, sexual content, graphic violence, or instructions for self-harm or \
wrongdoing. Content must be safe for advertisers.

5. NARRATION IS SPOKEN TEXT. Every `narration` value will be sent verbatim to a \
text-to-speech engine. Write plain spoken sentences only: no markdown, no stage \
directions, no bracketed cues, no emoji, no speaker labels, no URLs, no headings \
inside narration.

6. VISUAL PROMPTS ARE SEPARATE. Every `visual_prompt` describes footage to be \
generated for that segment: subject, setting, camera motion, lighting, mood. It \
must describe only generic scenes and must never name a real person, a real \
brand, a logo, or copyrighted characters.

OUTPUT CONTRACT

Return exactly one JSON object and nothing else. No prose before or after it, no \
markdown code fences. Keys:

  "title"        string, <= 100 characters, specific and honest, no clickbait \
that the script does not deliver on, no ALL-CAPS words.
  "description"  string, <= 4500 characters, plain text. First two sentences must \
stand alone as the search snippet. May end with a short chapter-free summary.
  "tags"         array of 8-15 lowercase strings, each <= 60 characters, no "#", \
no duplicates; combined length of all tags must stay under 450 characters.
  "segments"     array of objects, in playback order, each with:
                   "index"                integer starting at 1, consecutive
                   "heading"              string, <= 80 characters, internal \
working label only, never spoken
                   "narration"            string, spoken text for this segment
                   "visual_prompt"        string, <= 400 characters
                   "target_duration_sec"  integer, seconds this segment should \
occupy when spoken at a natural pace

The sum of "target_duration_sec" must be within 10 percent of the requested total \
duration.\
"""


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def target_segment_count(duration_sec: int) -> int:
    return _clamp(round(duration_sec / SECONDS_PER_SEGMENT), MIN_SEGMENTS, MAX_SEGMENTS)


def build_script_user_prompt(
    *,
    niche: str,
    custom_brief: str = "",
    brand_voice: str = "",
    banned_topics: list[str] | None = None,
    language: str = "en",
    duration_sec: int = 180,
    recent_titles: list[str] | None = None,
    regeneration_note: str = "",
) -> str:
    """Assemble the per-job brief. Empty optional fields are omitted entirely so
    the model never sees dangling "Brand voice: (none)" noise.
    """
    banned_topics = [t.strip() for t in (banned_topics or []) if t and t.strip()]
    recent_titles = [t.strip() for t in (recent_titles or []) if t and t.strip()]
    segments = target_segment_count(duration_sec)
    words_target = int(duration_sec / 60 * 150)

    parts: list[str] = [
        "PRODUCTION BRIEF",
        "",
        f"Niche / topic area: {niche}",
        (
            f"Spoken language: {language} (write the title, description, tags and "
            f"all narration in this language)"
        ),
        (
            f"Target total duration: {duration_sec} seconds "
            f"(~{words_target} spoken words at a natural pace)"
        ),
        f"Target number of segments: about {segments}",
    ]

    if custom_brief:
        parts += ["", "CREATOR BRIEF (highest priority after the safety rules):", custom_brief.strip()]

    if brand_voice:
        parts += [
            "",
            "BRAND VOICE — match this tone, vocabulary and audience level exactly:",
            brand_voice.strip(),
        ]

    if banned_topics:
        parts += [
            "",
            (
                "BANNED TOPICS — hard constraint. Do not mention, allude to, or build "
                "the video around any of the following, in the title, description, "
                "tags, narration or visual prompts:"
            ),
        ]
        parts += [f"  - {topic}" for topic in banned_topics]

    if recent_titles:
        parts += [
            "",
            (
                "ALREADY PUBLISHED ON THIS CHANNEL — choose a genuinely different "
                "subject and a different angle. Do not produce a rewording, a sequel, "
                "a 'part 2', or a near-synonym of any of these:"
            ),
        ]
        parts += [f"  - {title}" for title in recent_titles]

    if regeneration_note:
        parts += ["", "REGENERATION NOTE:", regeneration_note.strip()]

    parts += [
        "",
        "Now produce the JSON object described in the output contract. Return JSON only.",
    ]
    return "\n".join(parts)


def build_messages(system_prompt: str, user_prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def prompt_fingerprint(messages: list[dict]) -> str:
    """Stable hash of the exact prompt, stored in `video_jobs.script_meta`
    (SPEC 5.11: "model, prompt hash, token count") so a given output can always
    be traced back to the prompt revision that produced it.
    """
    payload = json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
