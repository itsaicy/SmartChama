from django.contrib import admin
from darajaapi.models import Transaction

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_user",
        "transaction_chama",
        "transaction_amount",
        "transaction_type",
        "transaction_status",
        "transaction_mpesa_receipt",
        "transaction_internal_reference",
        "transaction_created_at",
    )
    list_filter = (
        "transaction_status",
        "transaction_type",
        "transaction_chama",
    )
    search_fields = (
        "transaction_user__username",
        "transaction_phone_number",
        "transaction_mpesa_receipt",
        "transaction_internal_reference",
        "transaction_checkout_request_id",
        "transaction_merchant_request_id",
    )
    readonly_fields = (
        "transaction_created_at",
        "transaction_updated_at",
    )
    ordering = ("-transaction_created_at",)

    fieldsets = (
        ("User & Chama", {
            "fields": ("transaction_user", "transaction_chama")
        }),
        ("Transaction Details", {
            "fields": (
                "transaction_amount",
                "transaction_phone_number",
                "transaction_type",
                "transaction_status",
            )
        }),
        ("M-Pesa Metadata", {
            "fields": (
                "transaction_mpesa_receipt",
                "transaction_internal_reference",
                "transaction_checkout_request_id",
                "transaction_merchant_request_id",
            )
        }),
        ("Timestamps", {
            "fields": ("transaction_created_at", "transaction_updated_at")
        }),
    )
