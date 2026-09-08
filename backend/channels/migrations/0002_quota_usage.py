# Track C — SPEC 5.26 `quota_usage` (FR-58).
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("channels", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuotaUsage",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("google_project_id", models.CharField(max_length=64)),
                ("date_pt", models.DateField()),
                ("units_used", models.IntegerField(default=0)),
                ("uploads_used", models.IntegerField(default=0)),
                ("units_limit", models.IntegerField()),
                ("uploads_limit", models.IntegerField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "quota_usage"},
        ),
        migrations.AddConstraint(
            model_name="quotausage",
            constraint=models.UniqueConstraint(
                fields=("google_project_id", "date_pt"), name="uq_quota_usage_project_date"
            ),
        ),
    ]
