from django.contrib import admin

from providers.models import ApiCredentialConfig, ApiUsageLog


@admin.register(ApiCredentialConfig)
class ApiCredentialConfigAdmin(admin.ModelAdmin):
    """FR-84: admins pick provider/model and prices here.

    `secret_ref` is only the *name* of an env var — the key itself is never shown
    or stored, so this form cannot leak credentials (C-5, NFR-3). Rotation means
    changing the env var / secret store value, not this row.
    """

    list_display = (
        "service",
        "provider",
        "model_name",
        "is_primary",
        "is_active",
        "priority",
        "unit_cost_usd",
        "cost_unit",
        "secret_present",
    )
    list_filter = ("service", "provider", "is_primary", "is_active")
    search_fields = ("provider", "model_name", "display_name")

    @admin.display(boolean=True, description="Secret set")
    def secret_present(self, obj: ApiCredentialConfig) -> bool:
        return obj.has_secret()


@admin.register(ApiUsageLog)
class ApiUsageLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "provider",
        "model",
        "operation",
        "units",
        "unit_type",
        "cost_usd",
        "latency_ms",
        "success",
        "error_code",
    )
    list_filter = ("service", "provider", "success", "operation")
    search_fields = ("request_id", "model")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
