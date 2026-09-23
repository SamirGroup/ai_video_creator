from django.db import models


class AuthLogo(models.Model):
    name = models.CharField(max_length=100)
    image_url = models.URLField(max_length=2000)
    link_url = models.URLField(max_length=2000)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]


class Partner(models.Model):
    name = models.CharField(max_length=100)
    image_url = models.URLField(max_length=2000)
    link_url = models.URLField(max_length=2000)
    caption = models.CharField(max_length=160, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_affiliate = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "id"]


class PartnerBanner(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=True)
    title = models.CharField(max_length=120, default="Hamkorlarimiz")
    subtitle = models.CharField(
        max_length=240,
        blank=True,
        default="Biz bilan hamkorlik qilayotgan tashkilotlar va xizmatlar",
    )
    animation_enabled = models.BooleanField(default=True)
    animation_seconds = models.PositiveSmallIntegerField(default=35)
