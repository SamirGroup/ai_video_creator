from django.contrib import admin

from revenue.models import Invoice, LedgerEntry, RevenueRecord, RevenueShareStatement


@admin.register(RevenueRecord)
class RevenueRecordAdmin(admin.ModelAdmin):
    list_display = ("channel", "date", "source", "views", "estimated_revenue", "is_final")
    list_filter = ("source", "is_final")


@admin.register(RevenueShareStatement)
class RevenueShareStatementAdmin(admin.ModelAdmin):
    list_display = ("user", "period_start", "period_end", "gross_revenue", "status")
    list_filter = ("status",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "amount", "status", "due_at", "paid_at")
    list_filter = ("kind", "status")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("entry_uuid", "direction", "amount", "ref_type", "ref_id", "occurred_at")
    list_filter = ("direction", "ref_type")
    readonly_fields = [f.name for f in LedgerEntry._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
