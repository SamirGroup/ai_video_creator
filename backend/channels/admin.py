from django.contrib import admin

from channels.models import AdSenseAccount, YouTubeChannel


@admin.register(YouTubeChannel)
class YouTubeChannelAdmin(admin.ModelAdmin):
    list_display = ("channel_title", "youtube_channel_id", "user", "status", "is_monetized")
    list_filter = ("status", "is_monetized")
    search_fields = ("channel_title", "youtube_channel_id")
    # Encrypted token columns are intentionally excluded from every admin view (C-5, NFR-8).
    exclude = ("access_token_enc", "refresh_token_enc")


@admin.register(AdSenseAccount)
class AdSenseAccountAdmin(admin.ModelAdmin):
    list_display = ("adsense_account_id", "user", "status")
    list_filter = ("status",)
    exclude = ("access_token_enc", "refresh_token_enc")
