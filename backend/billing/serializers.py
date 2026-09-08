from rest_framework import serializers

from billing.models import Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "name",
            "price_amount",
            "currency",
            "billing_interval",
            "videos_per_period",
            "max_video_duration_sec",
            "max_languages",
            "concurrent_jobs",
            "voice_cloning_enabled",
            "priority_queue",
            "sla_hours",
            "features",
        ]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "current_period_start",
            "current_period_end",
            "cancel_at_period_end",
            "grace_period_ends_at",
            "revenue_share_paused",
        ]
        read_only_fields = fields
