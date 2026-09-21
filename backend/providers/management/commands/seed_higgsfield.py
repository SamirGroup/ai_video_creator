from decimal import Decimal

from billing.models import Plan
from django.core.management.base import BaseCommand
from django.db import transaction

from providers.models import ApiCredentialConfig


class Command(BaseCommand):
    help = "Add inactive Higgsfield models and plan entitlements without replacing admin prices."

    @transaction.atomic
    def handle(self, **options):
        models = []
        for tier, price in [("std", "0.063"), ("pro", "0.084"), ("4k", "0.21")]:
            name = f"kling-video/v3.0/{tier}/text-to-video"
            models.append(name)
            ApiCredentialConfig.objects.get_or_create(
                provider="higgsfield",
                service="video_gen",
                model_name=name,
                defaults={
                    "display_name": f"Kling 3.0 {tier.upper()} · Higgsfield",
                    "is_active": False,
                    "is_primary": False,
                    "secret_ref": "HF_KEY",
                    "unit_cost_usd": Decimal(price),
                    "cost_unit": "per_second",
                    "config": {
                        "allowed_durations": list(range(3, 16)),
                        "request_options": {"sound": "on", "multi_shots": False},
                        "pricing_source": "https://open.higgsfield.ai/pricing",
                        "pricing_verified_on": "2026-09-21",
                        "pricing_note": "Launch offer; verify before activation.",
                        "api_reference": f"https://open.higgsfield.ai/models/{name}/api-reference",
                    },
                },
            )
        for plan in Plan.objects.filter(code__in=["start", "pro", "pro_max", "ultra"]):
            features = dict(plan.features)
            permitted = models if plan.code in ["pro_max", "ultra"] else models[:2]
            features["video_models"] = list(
                dict.fromkeys(features.get("video_models", []) + permitted)
            )
            plan.features = features
            plan.save(update_fields=["features"])
        self.stdout.write(
            "Higgsfield catalog seeded inactive. Review prices and supply HF_KEY before activation."
        )
