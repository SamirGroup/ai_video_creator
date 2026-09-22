from core.models import TimestampedModel
from django.conf import settings
from django.db import models


class AssistantProfile(TimestampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    goal = models.CharField(max_length=1000, blank=True)
    audience_region = models.CharField(max_length=100, blank=True)
    language = models.CharField(max_length=20, default="uz")
    timezone = models.CharField(max_length=64, default="Asia/Tashkent")
    onboarding_completed = models.BooleanField(default=False)


class AssistantPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=True)
    daily_message_limit = models.PositiveSmallIntegerField(default=20)
    guidance = models.CharField(max_length=2000, blank=True)


class AssistantTurn(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    request_key = models.UUIDField()
    question = models.TextField()
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=20, default="pending")
    error_code = models.CharField(max_length=64, blank=True)
    cost_usd = models.DecimalField(max_digits=14, decimal_places=6, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request_key"], name="assistant_user_request"
            )
        ]
