from django.contrib import admin
from chama.models import Chama, Membership, JoinRequest

@admin.register(Chama)
class ChamaAdmin(admin.ModelAdmin):
    list_display = (
        "chama_name",
        "chama_created_by",
        "chama_contribution_amount",
        "chama_contribution_frequency",
        "chama_max_members",
        "chama_rota_type",
        "chama_payment_method",
        "chama_paybill_number",
        "chama_till_number",
        "chama_created_at",
    )

    search_fields = ("chama_name", "chama_description")
    list_filter = (
        "chama_contribution_frequency",
        "chama_rota_type",
        "chama_payment_method",
        "chama_created_at",
    )
    ordering = ("-chama_created_at",)
    readonly_fields = ("chama_created_at",)

    fieldsets = (
        ("Chama Details", {
            "fields": (
                "chama_name",
                "chama_description",
                "chama_created_by",
                "chama_contribution_amount",
                "chama_contribution_frequency",
                "chama_custom_frequency_days",
                "chama_max_members",
                "chama_rota_type",
            )
        }),

        ("Payment Method (Choose ONLY one)", {
            "fields": (
                "chama_payment_method",
                "chama_paybill_number",
                "chama_paybill_name",
                "chama_paybill_account_number",
                "chama_till_number",
                "chama_till_name",
            ),
            "description": "Select Paybill or Till. Do NOT fill both. The form will block invalid combinations."
        }),
        
        ("Metadata", {
            "fields": ("chama_created_at",),
        }),
    )



@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "membership_user",
        "membership_chama",
        "membership_role",
        "membership_status",
        "membership_join_date",
    )
    list_filter = ("membership_role", "membership_status")
    search_fields = (
        "membership_user__user_first_name",
        "membership_user__user_last_name",
        "membership_chama__chama_name",
    )
    ordering = ("-membership_join_date",)
    readonly_fields = ("membership_join_date",)


@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    list_display = (
        "join_request_user",
        "join_request_chama",
        "join_request_status",
        "join_request_requested_at",
        "join_request_reviewed_by",
        "join_request_reviewed_at",
    )
    list_filter = ("join_request_status", "join_request_requested_at")
    search_fields = (
        "join_request_user__user_first_name",
        "join_request_user__user_last_name",
        "join_request_chama__chama_name",
    )
    ordering = ("-join_request_requested_at",)
    readonly_fields = ("join_request_requested_at", "join_request_reviewed_at")

