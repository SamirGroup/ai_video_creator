from rest_framework import serializers

from video_pipeline.models import VideoJob, VideoJobStep
from video_pipeline.services.approval import RESTART_STAGES
from video_pipeline.services.prompts import (
    MAX_DESCRIPTION_BYTES,
    MAX_TAG_CHARS,
    MAX_TAGS_TOTAL_CHARS,
    MAX_TITLE_CHARS,
)


class VideoJobListSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoJob
        fields = [
            "id",
            "channel",
            "status",
            "current_stage",
            "scheduled_for",
            "title",
            "youtube_video_id",
            "published_at",
            "total_cost_usd",
            "created_at",
        ]
        read_only_fields = fields


class VideoJobDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoJob
        exclude: list[str] = []
        read_only_fields = [f.name for f in VideoJob._meta.fields]


class VideoJobStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoJobStep
        fields = "__all__"
        read_only_fields = [f.name for f in VideoJobStep._meta.fields]


# ---------------------------------------------------------------------------
# Approval flow (FR-38..FR-41)
# ---------------------------------------------------------------------------
class RequestChangesSerializer(serializers.Serializer):
    """POST /videos/{id}/request-changes body (FR-39)."""

    comment = serializers.CharField(max_length=4000, allow_blank=False, trim_whitespace=True)
    restart_stage = serializers.ChoiceField(choices=RESTART_STAGES)


class RejectVideoSerializer(serializers.Serializer):
    """POST /videos/{id}/reject body (FR-39)."""

    reason = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)


class VideoMetadataUpdateSerializer(serializers.Serializer):
    """PATCH /videos/{id}/metadata body (FR-41). Limits mirror the YouTube
    Data API constraints already enforced on generated scripts
    (`video_pipeline.services.prompts`).
    """

    title = serializers.CharField(
        required=False, allow_blank=False, trim_whitespace=True, max_length=MAX_TITLE_CHARS
    )
    description = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=MAX_TAG_CHARS, allow_blank=False, trim_whitespace=True),
        required=False,
    )

    def validate_description(self, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
            raise serializers.ValidationError(
                f"Description must be at most {MAX_DESCRIPTION_BYTES} bytes (UTF-8 encoded)."
            )
        return value

    def validate_tags(self, value: list[str]) -> list[str]:
        total_chars = sum(len(tag) for tag in value)
        if total_chars > MAX_TAGS_TOTAL_CHARS:
            raise serializers.ValidationError(
                f"Combined length of all tags must be at most {MAX_TAGS_TOTAL_CHARS} characters "
                f"(got {total_chars})."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        if not attrs:
            raise serializers.ValidationError("Provide at least one of: title, description, tags.")
        return attrs
