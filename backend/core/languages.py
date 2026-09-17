"""Shared content/UI locale registry. Never infer TTS support from this list."""

import json
from pathlib import Path

LANGUAGES = json.loads(
    Path(__file__).with_name("languages.json").read_text(encoding="utf-8")
)
LANGUAGE_CODES = tuple(item["code"] for item in LANGUAGES)
LANGUAGE_CHOICES = tuple((item["code"], item["name"]) for item in LANGUAGES)
DEFAULT_LANGUAGE = "ru"
_BY_CODE = {item["code"].lower(): item for item in LANGUAGES}


def language_info(code: str) -> dict:
    """Accept case/underscore variants while preserving canonical BCP-47 codes."""
    key = code.strip().replace("_", "-").lower()
    try:
        return _BY_CODE[key]
    except KeyError:
        raise ValueError(f"Unsupported language: {code}") from None


def normalize_language(code: str) -> str:
    return language_info(code)["code"]
