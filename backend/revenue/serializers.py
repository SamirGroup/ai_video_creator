from __future__ import annotations

from rest_framework import serializers

from revenue.models import Invoice, RevenueRecord, RevenueShareStatement


class RevenueRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RevenueRecord
        fields = [
            "id",
            "channel",
            "job",
            "youtube_video_id",
            "source",
            "date",
            "views",
            "estimated_minutes_watched",
            "estimated_revenue",
            "estimated_ad_revenue",
            "cpm",
            "rpm",
            "currency",
            "is_final",
        ]
        read_only_fields = fields


class RevenueShareStatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = RevenueShareStatement
        fields = [
            "id",
            "period_start",
            "period_end",
            "currency",
            "gross_revenue",
            "platform_share_pct",
            "platform_share_amount",
            "creator_share_amount",
            "video_count",
            "breakdown",
            "status",
            "finalized_at",
            "review_deadline",
            "disputed_at",
            "dispute_reason",
            "resolved_at",
            "carried_forward_from",
            "created_at",
        ]
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            "id",
            "statement",
            "kind",
            "amount",
            "currency",
            "status",
            "due_at",
            "paid_at",
            "attempts",
            "created_at",
        ]
        read_only_fields = fields


class DisputeStatementSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=2000, allow_blank=False, trim_whitespace=True
    )


class DateRangeSerializer(serializers.Serializer):
    """Shared `?from=&to=` query param validation for the summary/daily/by-video reads."""

    from_ = serializers.DateField(source="from", required=False)
    to = serializers.DateField(required=False)
