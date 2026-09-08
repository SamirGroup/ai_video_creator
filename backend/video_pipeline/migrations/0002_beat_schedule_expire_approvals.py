# Seeds the Celery Beat schedule for the FR-38 approval-timeout sweep
# (A-3: 48h window). Follows the same pattern as
# channels/migrations/0003_beat_schedules.py.
from django.db import migrations

TASK_NAME = "video_pipeline.expire_stale_approvals"


def seed(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = IntervalSchedule.objects.get_or_create(every=15, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={
            "task": TASK_NAME,
            "description": "FR-38/A-3: publish-or-expire video_jobs stuck in awaiting_approval > 48h.",
            "queue": "celery",
            "interval": schedule,
            "crontab": None,
            "enabled": True,
        },
    )


def unseed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("video_pipeline", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
