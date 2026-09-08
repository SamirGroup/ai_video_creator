# Seeds the Celery Beat schedule for the FR-67 monthly revenue-share period
# close (A-9: 10th of the month, after the FR-63 revision window has mostly
# settled). Follows the same pattern as channels/migrations/0003_beat_schedules.py.
from django.db import migrations

TASK_NAME = "revenue.close_revenue_period"


def seed(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="3",
        day_of_week="*",
        day_of_month="10",
        month_of_year="*",
        timezone="UTC",
    )
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={
            "task": TASK_NAME,
            "description": "FR-67/A-9: close the previous calendar month's revenue-share statements.",
            "queue": "celery",
            "crontab": schedule,
            "interval": None,
            "enabled": True,
        },
    )


def unseed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("revenue", "0002_stripe_connect_schema"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
