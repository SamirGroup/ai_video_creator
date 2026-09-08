from django.contrib import admin

from contracts.models import Contract, ContractVersion


@admin.register(ContractVersion)
class ContractVersionAdmin(admin.ModelAdmin):
    list_display = ("version", "title", "locale", "is_active", "effective_from")
    list_filter = ("is_active", "locale")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("user", "contract_version", "status", "signed_at")
    list_filter = ("status",)
    readonly_fields = ("signed_at", "body_sha256", "ip_address", "user_agent")
