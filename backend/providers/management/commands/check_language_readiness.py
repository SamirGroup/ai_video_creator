"""Check deployment TTS coverage without generating audio or making API calls."""

from django.core.management.base import BaseCommand, CommandError

from core.languages import LANGUAGE_CODES
from providers.exceptions import ProviderNotConfigured
from providers.language_routing import select_tts_config, voice_for_language


class Command(BaseCommand):
    help = "Check active TTS model, voice and secret configuration for all 30 content locales."

    def handle(self, *args, **options):
        unavailable = []
        for language in LANGUAGE_CODES:
            try:
                config = select_tts_config(language)
                missing = []
                if not voice_for_language(config, language):
                    missing.append("voice")
                if not config.has_secret():
                    missing.append("API credential")
                if config.provider == "azure_tts":
                    if not config.get_option("endpoint", "").startswith("https://"):
                        missing.append("HTTPS endpoint")
                    if not config.get_option("language_codes", {}).get(language):
                        missing.append("provider locale mapping")
                if missing:
                    raise ProviderNotConfigured("Missing " + ", ".join(missing))
                self.stdout.write(
                    f"{language}: configured ({config.provider}/{config.model_name}); live sample still required"
                )
            except ProviderNotConfigured as exc:
                unavailable.append(language)
                self.stdout.write(f"{language}: NOT READY — {exc}")
        if unavailable:
            raise CommandError(
                "TTS configuration incomplete for: " + ", ".join(unavailable)
            )
