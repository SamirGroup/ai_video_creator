from django.db import models


class AuthLogo(models.Model):
    name = models.CharField(max_length=100)
    image_url = models.URLField(max_length=2000)
    link_url = models.URLField(max_length=2000)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]
