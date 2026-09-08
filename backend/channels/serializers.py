from rest_framework import serializers

from channels.models import AdSenseAccount, YouTubeChannel


class YouTubeChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = YouTubeChannel
        # access_token_enc / refresh_token_enc are NEVER exposed via the API (C-5).
        fields = [
            "id",
            "youtube_channel_id",
            "channel_title",
            "channel_handle",
            "thumbnail_url",
            "subscriber_count",
            "video_count",
            "is_monetized",
            "monetization_source",
            "status",
            "last_error_code",
            "connected_at",
            "disconnected_at",
            "last_synced_at",
        ]
        read_only_fields = fields


class AdSenseAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdSenseAccount
        fields = ["id", "adsense_account_id", "status", "connected_at", "last_synced_at"]
        read_only_fields = fields
