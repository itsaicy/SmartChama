from django.db import models
from django.conf import settings
from chama.models import Chama
from finance.models import CONTRIBUTION_TYPE_CHOICES

TRANSACTION_STATUS_CHOICES = (
    ("pending", "Pending"),
    ("success", "Success"),
    ("failed", "Failed"),
)

class Transaction(models.Model):
    transaction_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        db_index=True,
        related_name="daraja_transactions"
    )
    transaction_chama = models.ForeignKey(
        Chama,
        on_delete=models.SET_NULL,
        null=True,
        db_index=True,
        related_name="daraja_transactions"
    )
    transaction_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    transaction_phone_number = models.CharField(max_length=15, null=True, blank=True)
    transaction_checkout_request_id = models.CharField(max_length=100, null=True, blank=True)
    transaction_merchant_request_id = models.CharField(max_length=100, null=True, blank=True)
    transaction_mpesa_receipt = models.CharField(max_length=20, null=True, blank=True)
    transaction_internal_reference = models.CharField(max_length=50, null=True, blank=True)
    transaction_type = models.CharField(
        max_length=20,
        choices=CONTRIBUTION_TYPE_CHOICES,
        db_index=True
    )
    transaction_status = models.CharField(
        max_length=20,
        choices=TRANSACTION_STATUS_CHOICES,
        default="pending",
        db_index=True
    )
    transaction_created_at = models.DateTimeField(auto_now_add=True)
    transaction_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["transaction_user", "transaction_status"]),
            models.Index(fields=["transaction_chama", "transaction_type"]),
            models.Index(fields=["transaction_internal_reference"]),  
        ]

    def __str__(self):
        return f"{self.transaction_user} — {self.transaction_type} — {self.transaction_status}"
