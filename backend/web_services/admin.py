from django.contrib import admin

from web_services.models import ExecutorProfile, ServiceOrder, ServicePackage


@admin.register(ServicePackage)
class ServicePackageAdmin(admin.ModelAdmin):
    list_display = ("code", "price_usd", "delivery_days", "support_months", "is_active")


@admin.register(ExecutorProfile)
class ExecutorProfileAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "tin", "sales_enabled")


@admin.register(ServiceOrder)
class ServiceOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "user", "package", "price_usd", "contract_type", "status", "created_at")
    exclude = ("contract_enc",)
    readonly_fields = [f.name for f in ServiceOrder._meta.fields if f.name != "contract_enc"]
