from rest_framework import serializers

from notifications.models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "type",
            "channel",
            "title",
            "body",
            "payload",
            "related_job",
            "status",
            "sent_at",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ["id", "type", "email_enabled", "in_app_enabled", "push_enabled"]
        read_only_fields = ["id", "type"]
