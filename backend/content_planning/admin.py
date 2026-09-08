from django.contrib import admin

from content_planning.models import ContentPreference


@admin.register(ContentPreference)
class ContentPreferenceAdmin(admin.ModelAdmin):
    list_display = ("channel", "niche", "frequency", "approval_mode", "is_paused")
    list_filter = ("frequency", "approval_mode", "is_paused")
