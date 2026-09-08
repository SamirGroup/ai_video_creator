from django.contrib import admin

from video_pipeline.models import MusicTrack, VideoAsset, VideoJob, VideoJobStep


@admin.register(VideoJob)
class VideoJobAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "channel", "status", "current_stage", "scheduled_for", "total_cost_usd")
    list_filter = ("status", "trigger")
    search_fields = ("youtube_video_id", "title")


@admin.register(VideoJobStep)
class VideoJobStepAdmin(admin.ModelAdmin):
    list_display = ("job", "stage", "attempt", "status", "provider", "duration_ms", "cost_usd")
    list_filter = ("stage", "status")

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(VideoAsset)
class VideoAssetAdmin(admin.ModelAdmin):
    list_display = ("job", "kind", "s3_key", "size_bytes")
    list_filter = ("kind",)


@admin.register(MusicTrack)
class MusicTrackAdmin(admin.ModelAdmin):
    list_display = ("title", "mood", "license_type", "is_active")
    list_filter = ("is_active", "license_type")
