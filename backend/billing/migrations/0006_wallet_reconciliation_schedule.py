from django.db import migrations


def seed(apps, schema_editor):
    Schedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    Task = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = Schedule.objects.get_or_create(
        minute="25",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    Task.objects.update_or_create(
        name="billing.reconcile_ai_wallets",
        defaults={
            "task": "billing.reconcile_ai_wallets",
            "crontab": schedule,
            "queue": "celery",
            "enabled": True,
        },
    )


def unseed(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(
        name="billing.reconcile_ai_wallets"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0005_aiwallethold"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]
    operations = [migrations.RunPython(seed, unseed)]
