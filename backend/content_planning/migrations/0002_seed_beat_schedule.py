"""Seed the two scheduler periodic tasks into django-celery-beat (ARCHITECTURE D-7).

Ops can tune the intervals in the Django admin; a fresh install still gets
the FR-35 schedule without manual setup.
"""
from __future__ import annotations

from django.db import migrations

TASKS = [
    ("content_planning.materialise_scheduled_jobs", "content_planning.tasks.materialise_scheduled_jobs", 15),
    ("content_planning.enqueue_due_jobs", "content_planning.tasks.enqueue_due_jobs", 5),
]


def seed(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    for name, task, minutes in TASKS:
        schedule, _ = IntervalSchedule.objects.get_or_create(every=minutes, period="minutes")
        PeriodicTask.objects.get_or_create(
            name=name,
            defaults={"task": task, "interval": schedule, "enabled": True, "queue": "celery"},
        )


def unseed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name__in=[name for name, _, _ in TASKS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content_planning", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
