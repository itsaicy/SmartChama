from django.contrib import admin
from .models import Penalty, ContributionCycle, Contribution, Loan, LoanRepayment


@admin.register(Penalty)
class PenaltyAdmin(admin.ModelAdmin):
    list_display = ("penalty_user", "penalty_chama", "penalty_amount", "penalty_reason", "penalty_created_at")
    search_fields = ("penalty_user__username", "penalty_chama__chama_name", "penalty_reason")
    list_filter = ("penalty_chama", "penalty_created_at")


@admin.register(ContributionCycle)
class ContributionCycleAdmin(admin.ModelAdmin):
    list_display = ("cycle_name", "cycle_chama", "cycle_type", "cycle_amount_required", "cycle_beneficiary", "cycle_deadline", "cycle_status", "cycle_created_at")
    search_fields = ("cycle_name", "cycle_chama__chama_name", "cycle_beneficiary__username")
    list_filter = ("cycle_type", "cycle_status", "cycle_chama")


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ("contribution_user", "contribution_chama", "contribution_cycle", "contribution_amount", "contribution_type", "contribution_status", "contribution_mpesa_receipt", "contribution_reference", "contribution_phone", "contribution_time", "contribution_created_at")
    search_fields = ("contribution_user__username", "contribution_chama__chama_name", "contribution_mpesa_receipt", "contribution_reference", "contribution_phone")
    list_filter = ("contribution_type", "contribution_status", "contribution_chama", "contribution_cycle")
    date_hierarchy = "contribution_time"


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("id", "loan_user", "loan_chama", "loan_amount", "loan_interest_rate", "loan_total_payable", "loan_purpose", "loan_status", "loan_deadline", "loan_outstanding_balance", "loan_reference", "loan_created_at")
    search_fields = ("loan_user__username", "loan_chama__chama_name", "loan_purpose", "loan_reference")
    list_filter = ("loan_status", "loan_chama", "loan_deadline")
    date_hierarchy = "loan_deadline"


@admin.register(LoanRepayment)
class LoanRepaymentAdmin(admin.ModelAdmin):
    list_display = ("loan_repayment_loan", "loan_repayment_user", "loan_repayment_amount", "loan_repayment_time", "loan_repayment_mpesa_receipt", "loan_repayment_reference")
    search_fields = ("loan_repayment_user__username", "loan_repayment_loan__id", "loan_repayment_mpesa_receipt", "loan_repayment_reference")
    list_filter = ("loan_repayment_time", "loan_repayment_user")
    date_hierarchy = "loan_repayment_time"
