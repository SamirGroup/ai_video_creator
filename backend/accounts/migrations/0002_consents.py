# Track A: SPEC 5.28 `consents` (Consent model only; other accounts models belong to Track E).

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Consent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("consent_type", models.CharField(max_length=64)),
                ("granted", models.BooleanField()),
                ("scope_details", models.JSONField(blank=True, default=dict)),
                ("granted_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True, default="")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="consents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "consents",
                "indexes": [
                    models.Index(
                        fields=["user", "consent_type", "granted_at"],
                        name="ix_consents_user_type_at",
                    )
                ],
            },
        ),
    ]
