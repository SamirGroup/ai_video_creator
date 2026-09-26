from django.contrib import admin

from payoneer.models import PayoneerAccount, PayoneerPayee, PayoneerPayout


@admin.register(PayoneerAccount)
class PayoneerAccountAdmin(admin.ModelAdmin):
    list_display = ("label", "environment", "is_active", "is_default_checkout", "is_default_payouts")
    exclude = ("payment_token_enc", "client_secret_enc", "notification_token_enc")


@admin.register(PayoneerPayee)
class PayoneerPayeeAdmin(admin.ModelAdmin):
    list_display = ("display_name", "payee_id", "account", "status")


@admin.register(PayoneerPayout)
class PayoneerPayoutAdmin(admin.ModelAdmin):
    list_display = ("client_reference_id", "payee", "amount", "currency", "status", "created_at")
    readonly_fields = [f.name for f in PayoneerPayout._meta.fields]
