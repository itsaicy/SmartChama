from django.db import models
from django.conf import settings
from chama.models import Chama

CONTRIBUTION_TYPE_CHOICES = (
    ('contribution', "Contribution"),
    ('penalty', "Penalty"),
    ('loan_repayment', "Loan Repayment"),
    ('registration_fee', "Registration Fee"),
)

CYCLE_TYPE_CHOICES = (
    ('fixed_rota', "Fixed Rota"),
    ('manual', "Manual Selection"),
    ('merrygoround', "Merry-Go Round"),
    ('shared_split', "Shared Split"),
)

LOAN_STATUS_CHOICES = (
    ('pending', "Pending"),
    ('approved', "Approved"),
    ('rejected', "Rejected"),
    ('active', "Active"),
    ('completed', "Completed"),
    ('defaulted', "Defaulted"),
)
class Penalty(models.Model):
    penalty_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    penalty_chama = models.ForeignKey(Chama, on_delete=models.CASCADE)
    penalty_amount = models.FloatField()
    penalty_reason = models.TextField()
    penalty_paid = models.BooleanField(default=False)
    penalty_created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.penalty_user} - {self.penalty_amount}"


class ContributionCycle(models.Model):
    cycle_chama = models.ForeignKey(Chama, on_delete=models.CASCADE, related_name="cycles")
    cycle_name = models.CharField(max_length=100)
    cycle_type = models.CharField(max_length=20, choices=CYCLE_TYPE_CHOICES)
    cycle_amount_required = models.DecimalField(max_digits=10, decimal_places=2)
    cycle_beneficiary = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="cycle_beneficiary"
    )
    cycle_deadline = models.DateField()
    cycle_status = models.CharField(max_length=20, default="open")
    cycle_created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.cycle_name} — {self.cycle_type}"

class Contribution(models.Model):
    contribution_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_index=True)
    contribution_chama = models.ForeignKey(Chama, on_delete=models.CASCADE, db_index=True)
    contribution_cycle = models.ForeignKey(
        ContributionCycle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contributions"
    )
    contribution_status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("success", "Success"), ("failed", "Failed")],
        default="pending",
        db_index=True
    )
    contribution_amount = models.DecimalField(max_digits=10, decimal_places=2)
    contribution_type = models.CharField(max_length=20, choices=CONTRIBUTION_TYPE_CHOICES, default='contribution', db_index=True)
    contribution_mpesa_receipt = models.CharField(max_length=20, blank=True, null=True)
    contribution_reference = models.CharField(max_length=50, blank=True, null=True)
    contribution_phone = models.CharField(max_length=15)
    contribution_time = models.DateTimeField()
    contribution_created_at = models.DateTimeField(auto_now_add=True)
    contribution_updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.contribution_user} — {self.contribution_type} — {self.contribution_amount}"

class Loan(models.Model):
    loan_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="loans")
    loan_chama = models.ForeignKey(Chama, on_delete=models.CASCADE, related_name="loans")
    loan_amount = models.DecimalField(max_digits=10, decimal_places=2)
    loan_interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    loan_total_payable = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    loan_purpose = models.CharField(max_length=255)
    loan_status = models.CharField(max_length=20, choices=LOAN_STATUS_CHOICES, default='pending')
    loan_deadline = models.DateField()
    loan_outstanding_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    loan_reference = models.CharField(max_length=50, blank=True, null=True)
    loan_created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Loan {self.id} — {self.loan_user} — {self.loan_status}"

class LoanRepayment(models.Model):
    loan_repayment_loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='repayments')
    loan_repayment_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    loan_repayment_amount = models.DecimalField(max_digits=10, decimal_places=2)
    loan_repayment_time = models.DateTimeField(auto_now_add=True)
    loan_repayment_mpesa_receipt = models.CharField(max_length=20, null=True, blank=True)
    loan_repayment_reference = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"{self.loan_repayment_loan} — {self.loan_repayment_amount}"
