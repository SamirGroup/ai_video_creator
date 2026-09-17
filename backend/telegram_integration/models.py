from django.conf import settings
from django.db import models
from core.models import TimestampedModel


class TelegramConfig(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    stars_net_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    enabled = models.BooleanField(default=False)
    channel_id = models.CharField(max_length=64, blank=True)
    bot_username = models.CharField(max_length=64, blank=True)
    token_secret_ref = models.CharField(max_length=100, default="TELEGRAM_BOT_TOKEN")
    webhook_secret_ref = models.CharField(
        max_length=100, default="TELEGRAM_WEBHOOK_SECRET"
    )


class TelegramIdentity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    telegram_id = models.BigIntegerField(unique=True)


class TelegramArchive(TimestampedModel):
    job = models.OneToOneField("video_pipeline.VideoJob", on_delete=models.CASCADE)
    channel_id = models.CharField(max_length=64)
    checksum = models.CharField(max_length=64)
    parts = models.JSONField(default=list)
    status = models.CharField(max_length=20, default="pending")
    error = models.CharField(max_length=200, blank=True)


class TelegramUpdate(models.Model):
    update_id = models.BigIntegerField(primary_key=True)
    processed_at = models.DateTimeField(auto_now_add=True)


class StarsOrder(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    plan = models.ForeignKey("billing.Plan", on_delete=models.PROTECT)
    telegram_id = models.BigIntegerField()
    stars = models.PositiveIntegerField()
    net_usd = models.DecimalField(max_digits=14, decimal_places=2)
    tax_usd = models.DecimalField(max_digits=14, decimal_places=2)
    precheckout_id = models.CharField(max_length=255, null=True, blank=True)
    charge_id = models.CharField(max_length=255, unique=True, null=True)
    paid_at = models.DateTimeField(null=True)
