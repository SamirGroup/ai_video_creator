from django.apps import AppConfig


class VideoPipelineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "video_pipeline"
    verbose_name = "Video Pipeline"

    def ready(self):
        # Celery's autodiscover only imports <app>.tasks; the YouTube sweep
        # tasks live in tasks_youtube and must be registered explicitly, or
        # beat's schedule (FR-59) hits an unregistered-task error.
        from . import tasks_youtube  # noqa: F401
