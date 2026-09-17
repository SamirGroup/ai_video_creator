from django.db.models.signals import post_save
from django.dispatch import receiver
from providers.models import ApiUsageLog
from video_pipeline.models import VideoJob
from billing.wallet import debit_usage, release_job


@receiver(post_save, sender=ApiUsageLog)
def account_usage(sender, instance, created, **kwargs):
    if created:
        debit_usage(instance)


@receiver(post_save, sender=VideoJob)
def release_finished_budget(sender, instance, **kwargs):
    if instance.status in {
        "published",
        "failed",
        "canceled",
        "rejected",
        "expired",
        "moderation_rejected",
        "awaiting_approval",
    }:
        release_job(instance)
