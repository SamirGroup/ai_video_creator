"""Real inference smoke test without changing the database or live provider."""

import json

from django.core.management.base import BaseCommand, CommandError
from video_pipeline.services.ollama_client import OllamaClient

from providers.exceptions import ProviderError
from providers.models import ApiCredentialConfig


class Command(BaseCommand):
    help = "Test local Uzbek text and structured planning without activating or writing customer data."

    def add_arguments(self, parser):
        parser.add_argument("--model", default="qwen3:4b-instruct")

    def handle(self, **options):
        config = ApiCredentialConfig(
            provider="ollama",
            service="llm",
            model_name=options["model"],
            config={"context_tokens": 4096, "request_timeout_sec": 120},
        )
        client = OllamaClient(config)
        cases = [
            (
                False,
                "O‘zbek tilida, lotin yozuvida ikki qisqa gap bilan video yaratuvchiga kontent reja nima ekanini tushuntiring.",
            ),
            (
                True,
                'Return only JSON with key "items": an array of exactly 2 objects, each with "title" and "hook" strings in Uzbek Latin. Suggest cooking video ideas. No other fields.',
            ),
        ]
        for structured, prompt in cases:
            try:
                result = client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    json_mode=structured,
                    max_tokens=300,
                )
                if structured:
                    items = json.loads(result.content)["items"]
                    if len(items) != 2 or any(
                        not isinstance(x.get("title"), str)
                        or not isinstance(x.get("hook"), str)
                        for x in items
                    ):
                        raise ValueError("Unexpected plan shape")
            except (ProviderError, ValueError, KeyError, TypeError) as exc:
                raise CommandError(f"Local inference test failed: {exc}") from None
            self.stdout.write(
                json.dumps(
                    {
                        "structured": structured,
                        "latency_ms": result.latency_ms,
                        "tokens": result.total_tokens,
                        "response": result.content,
                    },
                    ensure_ascii=False,
                )
            )
