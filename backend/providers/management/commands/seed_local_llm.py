from decimal import Decimal

from django.core.management.base import BaseCommand

from providers.models import ApiCredentialConfig


class Command(BaseCommand):
    help = (
        "Register an inactive self-hosted Qwen provider; never switch a live provider."
    )

    def add_arguments(self, parser):
        parser.add_argument("--model", default="qwen3:4b-instruct")

    def handle(self, **options):
        config, created = ApiCredentialConfig.objects.get_or_create(
            service="llm",
            provider="ollama",
            deleted_at__isnull=True,
            defaults={
                "model_name": options["model"],
                "display_name": "Qwen · Private Ollama",
                "is_active": False,
                "is_primary": False,
                "cost_unit": "per_1k_tokens",
                "unit_cost_usd": Decimal(0),
                "config": {
                    "input_cost_per_1k_usd": "0",
                    "output_cost_per_1k_usd": "0",
                    "context_tokens": 16384,
                    "max_output_tokens": 4000,
                    "request_timeout_sec": 120,
                    "json_mode": True,
                    "pricing_note": "No per-token provider invoice; hosting costs are accounted separately.",
                },
            },
        )
        self.stdout.write(
            f"Local provider {'registered inactive' if created else 'already exists; unchanged'}: {config.model_name}"
        )
