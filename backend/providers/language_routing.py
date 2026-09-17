"""Select only an explicitly language-capable TTS model before spending money.

Built-in capabilities: https://elevenlabs.io/docs/help-center/other/what-languages-do-you-support
Other models must declare config.supported_languages (exact BCP-47 locales).
"""

from core.languages import normalize_language
from providers.exceptions import ProviderNotConfigured
from providers.models import ApiCredentialConfig, ServiceType

_V2 = set("en ja zh de hi fr ko pt it es id tr pl ar uk ru".split())
_V3 = _V2 | set("az bn ka ha kk ky fa th ur vi".split())


def supports_language(config, language: str) -> bool:
    language = normalize_language(language)
    declared = config.get_option("supported_languages", None)
    if declared is not None:
        return language in declared
    if config.provider != "elevenlabs":
        return False
    languages = (
        _V3
        if config.model_name == "eleven_v3"
        else _V2
        if config.model_name == "eleven_multilingual_v2"
        else set()
    )
    # A regional dialect needs explicit voice/model configuration; base Arabic
    # support alone is not evidence of Egyptian pronunciation.
    return language in languages


def select_tts_config(language: str):
    language = normalize_language(language)
    candidates = ApiCredentialConfig.objects.filter(
        service=ServiceType.TTS,
        is_active=True,
        deleted_at__isnull=True,
    ).order_by("-is_primary", "priority", "created_at")
    for config in candidates:
        if supports_language(config, language) and config.provider in {
            "elevenlabs",
            "azure_tts",
        }:
            return config
    raise ProviderNotConfigured(
        f"No active TTS provider supports '{language}'. Configure a supported model and voice for this language."
    )


def voice_for_language(config, language: str) -> str:
    return str(
        config.get_option("voices", {}).get(language)
        or config.get_option("default_voice_id", "")
        or ""
    )
