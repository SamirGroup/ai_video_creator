from django.contrib import admin

from billing.models import Plan, Subscription, WebhookEvent


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "price_amount", "currency", "billing_interval", "is_active")
    list_filter = ("is_active", "billing_interval")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "current_period_end", "revenue_share_paused")
    list_filter = ("status", "revenue_share_paused")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_type", "event_id", "status", "received_at")
    list_filter = ("provider", "status")
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]

    def has_add_permission(self, request):
        return False
