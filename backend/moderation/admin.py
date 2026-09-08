from django.contrib import admin

from moderation.models import ModerationLog


@admin.register(ModerationLog)
class ModerationLogAdmin(admin.ModelAdmin):
    list_display = ("job", "stage", "provider", "verdict", "review_decision", "created_at")
    list_filter = ("stage", "verdict", "review_decision")
