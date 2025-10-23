from django.db import models
from user.models import User


class Chama(models.Model):
    chama_name = models.CharField(max_length=50)
    chama_description = models.CharField(max_length=100)
    chama_created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    chama_created_at = models.DateTimeField(auto_now_add=True)
    chama_contribution_amount = models.FloatField()
    chama_contribution_frequency = models.CharField(
        max_length=20,
        choices=[
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('custom', 'Custom'),
        ],
        default='monthly'
    )
    chama_custom_frequency_days = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="If custom, enter number of days between contributions."
    )
    chama_max_members = models.PositiveIntegerField(default=10)
    chama_rota_type = models.CharField(
        max_length=14,
        choices=[
            ('fixed', 'Fixed Order'),
            ('random', 'Randomized'),
            ('manual', 'Manual Selection'),
        ],
        default='fixed'
    )
    
    def __str__(self):
        return self.chama_name


class Membership(models.Model):
    membership_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    membership_chama = models.ForeignKey(Chama, on_delete=models.CASCADE, related_name='members')
    membership_join_date = models.DateTimeField(auto_now_add=True)
    membership_status = models.CharField(
        max_length=8,
        choices=[
            ('active', 'Active'),
            ('inactive', 'Inactive')
        ],
        default='active'
    )
    membership_role = models.CharField(
        max_length=9,
        choices=[
            ('member', 'Member'),
            ('admin', 'Admin'),
            ('treasurer', 'Treasurer'),
            ('secretary', 'Secretary')
        ],
        default='member'
    )

    def __str__(self):
        return f"{self.membership_user.user_first_name}\
              {self.membership_user.user_last_name} - {self.membership_chama.chama_name}"


class JoinRequest(models.Model):
    join_request_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='join_requests')
    join_request_chama = models.ForeignKey(Chama, on_delete=models.CASCADE, related_name='join_requests')
    join_request_status = models.CharField(
        max_length=8,
        choices=[
            ('pending', 'Pending'),
            ('accepted', 'Accepted'),
            ('rejected', 'Rejected'),
        ],
        default='pending'
    )
    join_request_requested_at = models.DateTimeField(auto_now_add=True)
    join_request_reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_join_requests'
    )
    join_request_reviewed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.join_request_user.user_first_name} \
            {self.join_request_user.user_last_name} → {self.join_request_chama.chama_name} ({self.join_request_status})"
