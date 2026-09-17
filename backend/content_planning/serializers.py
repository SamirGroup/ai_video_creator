"""FR-33/FR-34 content preference validation."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from rest_framework import serializers

from billing.quota import plan_limits_for
from content_planning.models import ContentPreference, Frequency
from core.languages import normalize_language


class ContentPreferenceSerializer(serializers.ModelSerializer):
    """Create/update serializer. Pass `context={"user": request.user}` so the
    plan's `max_video_duration_sec` cap can be enforced (FR-23).
    """

    class Meta:
        model = ContentPreference
        fields = [
            "id",
            "channel",
            "niche",
            "custom_brief",
            "brand_voice",
            "banned_topics",
            "language",
            "video_duration_sec",
            "aspect_ratio",
            "frequency",
            "publish_time_local",
            "publish_timezone",
            "publish_days",
            "youtube_privacy_status",
            "youtube_category_id",
            "made_for_kids",
            "approval_mode",
            "auto_publish_on_timeout",
            "voice_id",
            "music_style",
            "is_paused",
            "automatic_schedule_enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "channel", "is_paused", "created_at", "updated_at"]
        extra_kwargs = {
            "custom_brief": {"max_length": 4000},
            "brand_voice": {"max_length": 4000},
        }

    def validate_niche(self, value: str) -> str:
        value = value.strip().lower()
        if value not in settings.CONTENT_NICHES:
            raise serializers.ValidationError(
                f"Unknown niche. Choose one of: {', '.join(settings.CONTENT_NICHES)}."
            )
        return value

    def validate_language(self, value: str) -> str:
        try:
            value = normalize_language(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from None
        if value not in settings.SUPPORTED_CONTENT_LANGUAGES:
            raise serializers.ValidationError(
                f"Only {', '.join(settings.SUPPORTED_CONTENT_LANGUAGES)} content is supported in this release."
            )
        return value

    def validate_video_duration_sec(self, value: int) -> int:
        lo, hi = settings.VIDEO_DURATION_MIN_SEC, settings.VIDEO_DURATION_MAX_SEC
        if not lo <= value <= hi:
            raise serializers.ValidationError(
                f"Video duration must be between {lo} and {hi} seconds."
            )
        user = self.context.get("user")
        if user is not None:
            limits = plan_limits_for(user)
            if value > limits.max_video_duration_sec:
                raise serializers.ValidationError(
                    f"Your {limits.code} plan allows videos up to {limits.max_video_duration_sec} seconds. "
                    "Upgrade to produce longer videos."
                )
        return value

    def validate_publish_timezone(self, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            raise serializers.ValidationError(
                "Unknown IANA timezone (e.g. 'Europe/London')."
            ) from None
        return value

    def validate_banned_topics(self, value: list[str]) -> list[str]:
        cleaned = [t.strip() for t in value if t and t.strip()]
        if len(cleaned) > 50:
            raise serializers.ValidationError("At most 50 banned topics.")
        return cleaned

    def validate_youtube_category_id(self, value: str) -> str:
        if not value.isdigit():
            raise serializers.ValidationError("YouTube category id must be numeric.")
        return value

    def validate(self, attrs):
        frequency = attrs.get("frequency", getattr(self.instance, "frequency", None))
        days = attrs.get("publish_days", getattr(self.instance, "publish_days", None))
        if frequency == Frequency.WEEKLY:
            if not days:
                raise serializers.ValidationError(
                    {
                        "publish_days": "Weekly schedules need at least one weekday (0=Monday .. 6=Sunday)."
                    }
                )
            bad = [d for d in days if not 0 <= int(d) <= 6]
            if bad:
                raise serializers.ValidationError(
                    {
                        "publish_days": "Weekdays must be between 0 (Monday) and 6 (Sunday)."
                    }
                )
            attrs["publish_days"] = sorted({int(d) for d in days})
        elif frequency == Frequency.MONTHLY:
            if days:
                if len(days) != 1 or not 1 <= int(days[0]) <= 28:
                    raise serializers.ValidationError(
                        {
                            "publish_days": "Monthly schedules take a single day of month between 1 and 28."
                        }
                    )
                attrs["publish_days"] = [int(days[0])]
        elif frequency == Frequency.DAILY and "publish_days" in attrs:
            attrs["publish_days"] = None
        return attrs


class ContentPreferenceReadSerializer(ContentPreferenceSerializer):
    """Read-only projection (same fields) with the channel id exposed as a plain UUID."""

    channel = serializers.UUIDField(source="channel_id", read_only=True)


class GenerateVideoSerializer(serializers.Serializer):
    """Body of POST /videos/generate (FR-36)."""

    channel_id = serializers.UUIDField(required=False)
