from decimal import Decimal

from django.db import migrations

# Each tier doubles the price; scope, time and support grow with it.
PACKAGES = [
    # code, price, days, revisions, support months, pages (0 = by spec), languages
    ("starter", "800.00", 14, 2, 1, 1, 1),
    ("business", "1600.00", 25, 3, 2, 8, 2),
    ("pro", "3200.00", 40, 4, 3, 20, 3),
    ("enterprise", "6400.00", 60, 5, 6, 0, 5),
]


def seed(apps, schema_editor):
    Package = apps.get_model("web_services", "ServicePackage")
    for order, (code, price, days, revisions, support, pages, languages) in enumerate(PACKAGES):
        Package.objects.update_or_create(
            code=code,
            defaults={
                "sort_order": order,
                "price_usd": Decimal(price),
                "delivery_days": days,
                "revision_rounds": revisions,
                "support_months": support,
                "page_limit": pages,
                "languages": languages,
            },
        )
    apps.get_model("web_services", "ExecutorProfile").objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("web_services", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
