from __future__ import annotations

from rest_framework import serializers

from moderation.models import ModerationLog
from video_pipeline.models import VideoJob


class ModerationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModerationLog
        fields = [
            "id",
            "stage",
            "provider",
            "verdict",
            "categories",
            "threshold_config",
            "reviewed_by",
            "review_decision",
            "review_reason",
            "reviewed_at",
            "created_at",
        ]
        read_only_fields = fields


class ModerationQueueItemSerializer(serializers.ModelSerializer):
    """One row of `GET /admin/moderation/queue` (FR-81): the job plus the
    moderation_logs row that put it there.
    """

    latest_log = serializers.SerializerMethodField()

    class Meta:
        model = VideoJob
        fields = [
            "id",
            "user",
            "channel",
            "title",
            "status",
            "current_stage",
            "created_at",
            "updated_at",
            "latest_log",
        ]
        read_only_fields = fields

    def get_latest_log(self, job: VideoJob) -> dict | None:
        log = job.moderation_logs.order_by("-created_at").first()
        return ModerationLogSerializer(log).data if log else None


class ModerationDecisionSerializer(serializers.Serializer):
    """POST /admin/moderation/{job_id}/decide body (FR-81: `reason` mandatory both ways)."""

    decision = serializers.ChoiceField(choices=["approved", "rejected"])
    reason = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)
