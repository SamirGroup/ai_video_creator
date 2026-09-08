# Track C — seed Celery Beat schedules (ARCHITECTURE D-7: stored in DB via
# django-celery-beat so ops can tune them, seeded here so fresh installs get them).
#
# * channels.refresh_expiring_channel_tokens  every 15 min  (FR-14)
# * video_pipeline.check_recent_uploads       every 30 min  (FR-59)
# * video_pipeline.sync_published_videos      daily 03:30 UTC (FR-60) — before
#   the 04:00 UTC revenue sync so deleted videos are excluded the same day.
#
# Tasks are referenced by *name* only, so this migration has no dependency on
# video_pipeline migrations (avoids merge conflicts with Track B's 0002).
from django.db import migrations

SCHEDULES = [
    {
        "name": "channels.refresh_expiring_channel_tokens",
        "task": "channels.refresh_expiring_channel_tokens",
        "interval": {"every": 15, "period": "minutes"},
        "description": "FR-14: refresh YouTube OAuth tokens expiring within 30 minutes.",
    },
    {
        "name": "video_pipeline.check_recent_uploads",
        "task": "video_pipeline.check_recent_uploads",
        "interval": {"every": 30, "period": "minutes"},
        "description": "FR-59: poll YouTube processing/rejection status for videos published < 24h ago.",
    },
    {
        "name": "video_pipeline.sync_published_videos",
        "task": "video_pipeline.sync_published_videos",
        "crontab": {"minute": "30", "hour": "3"},
        "description": "FR-60: detect platform videos deleted/re-privatised on YouTube.",
    },
]


def seed(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    for spec in SCHEDULES:
        defaults = {
            "task": spec["task"],
            "description": spec["description"],
            "queue": "celery",
            "enabled": True,
        }
        if "interval" in spec:
            schedule, _ = IntervalSchedule.objects.get_or_create(**spec["interval"])
            defaults["interval"] = schedule
            defaults["crontab"] = None
        else:
            cron = {
                "minute": "*",
                "hour": "*",
                "day_of_week": "*",
                "day_of_month": "*",
                "month_of_year": "*",
                "timezone": "UTC",
            }
            cron.update(spec["crontab"])
            schedule, _ = CrontabSchedule.objects.get_or_create(**cron)
            defaults["crontab"] = schedule
            defaults["interval"] = None
        PeriodicTask.objects.update_or_create(name=spec["name"], defaults=defaults)


def unseed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name__in=[spec["name"] for spec in SCHEDULES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("channels", "0002_quota_usage"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
