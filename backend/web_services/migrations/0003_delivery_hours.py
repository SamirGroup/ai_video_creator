import django.core.validators
from django.db import migrations, models

# AI-assisted delivery: Start 1–2 hours, Business 1 day, Pro 2 days,
# Enterprise 3 days. Existing orders keep the terms frozen in their contract.
HOURS = {"starter": (1, 2), "business": (None, 24), "pro": (None, 48), "enterprise": (None, 72)}


def set_hours(apps, schema_editor):
    Package = apps.get_model("web_services", "ServicePackage")
    for package in Package.objects.all():
        low, high = HOURS.get(package.code, (None, package.delivery_days * 24))
        package.delivery_hours_min, package.delivery_hours = low, high
        package.save(update_fields=["delivery_hours_min", "delivery_hours"])


class Migration(migrations.Migration):
    dependencies = [("web_services", "0002_seed_packages")]

    operations = [
        migrations.AddField(
            model_name="servicepackage",
            name="delivery_hours_min",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="servicepackage",
            name="delivery_hours",
            field=models.PositiveSmallIntegerField(
                default=24, validators=[django.core.validators.MinValueValidator(1)]
            ),
            preserve_default=False,
        ),
        migrations.RunPython(set_hours, migrations.RunPython.noop),
        migrations.RemoveField(model_name="servicepackage", name="delivery_days"),
    ]
