from django.db import migrations


def seed(apps, schema_editor):
    Schedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    Task = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = Schedule.objects.get_or_create(
        minute="15",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    Task.objects.update_or_create(
        name="revenue.finalize_reviewed_statements",
        defaults={
            "task": "revenue.finalize_reviewed_statements",
            "crontab": schedule,
            "interval": None,
            "queue": "celery",
            "enabled": True,
        },
    )


def unseed(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(
        name="revenue.finalize_reviewed_statements"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("revenue", "0005_revenuesharestatement_review_deadline_and_more"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]
    operations = [migrations.RunPython(seed, unseed)]
