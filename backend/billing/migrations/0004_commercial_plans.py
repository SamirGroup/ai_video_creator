from decimal import Decimal
from django.db import migrations


def seed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Provider = apps.get_model("providers", "ApiCredentialConfig")
    models = [
        ("gen4.5", "Runway Gen-4.5", "0.12", [5, 10], {}),
        (
            "veo3.1_fast",
            "Google Veo 3.1 Fast via Runway",
            "0.10",
            [4, 6, 8],
            {"audio": False},
        ),
        ("veo3.1", "Google Veo 3.1 via Runway", "0.20", [4, 6, 8], {"audio": False}),
    ]
    for model, name, price, durations, options in models:
        Provider.objects.get_or_create(
            service="video_gen",
            provider="runway",
            model_name=model,
            defaults={
                "display_name": name,
                "is_active": False,
                "is_primary": False,
                "secret_ref": "RUNWAY_API_KEY",
                "cost_unit": "per_second",
                "unit_cost_usd": Decimal(price),
                "config": {
                    "base_url": "https://api.dev.runwayml.com/v1",
                    "create_path": "text_to_video",
                    "allowed_durations": durations,
                    "request_options": options,
                    "pricing_source": "https://docs.dev.runwayml.com/guides/pricing/",
                    "pricing_verified_on": "2026-09-17",
                    "pricing_currency": "USD",
                    "audio": False,
                },
            },
        )
    for code, name, price, order in [
        ("start", "Start", 20, 1),
        ("pro", "Pro", 50, 2),
        ("pro_max", "Pro Max", 100, 3),
        ("ultra", "Ultra", 200, 4),
    ]:
        available = ["veo3.1_fast", "gen4.5"] + (["veo3.1"] if order >= 3 else [])
        Plan.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "price_amount": price,
                "currency": "USD",
                "billing_interval": "month",
                "tax_pct": 12,
                "ai_budget_enabled": True,
                "videos_per_period": int(price) // 5,
                "max_video_duration_sec": 60 * order,
                "max_languages": 30,
                "concurrent_jobs": min(order, 3),
                "sort_order": order,
                "features": {
                    "video_models": available,
                    "ai_share_pct": 70,
                    "platform_share_pct": 30,
                    "credit_usd": "0.0001",
                    "job_budget_usd": str(Decimal(price) * Decimal("0.35")),
                    "quota_description": "Subject to actual AI credit balance; video count is a safety cap, not a prepaid guarantee.",
                },
            },
        )
    Plan.objects.filter(code__in=["starter", "professional", "enterprise"]).update(
        is_active=False
    )


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0003_plan_ai_budget_enabled_plan_discount_ends_at_and_more"),
        ("providers", "0002_seed_default_providers"),
    ]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
