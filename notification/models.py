from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from chama.models import Chama
from finance.models import Loan, Contribution, Penalty

class UserNotificationSettings(models.Model):
    user_notification_settings_user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    user_notification_settings_allow_sms = models.BooleanField(default=True)
    user_notification_settings_allow_email = models.BooleanField(default=True)
    user_notification_settings_allow_inapp = models.BooleanField(default=True)
    user_notification_settings_fallback = models.BooleanField(default=True)

    def __str__(self):
        return f"Notification Settings for {self.user_notification_settings_user}"


class Notification(models.Model):
    NOTIFICATION_TYPE = [
        ('reminder', 'Reminder'),
        ('loan', 'Loan'),
        ('payment', 'Payment'),
        ('meeting', 'Meeting'),
        ('announcement', 'Announcement'),
        ('member_joined', 'Member Joined'),
        ('transaction', 'Transaction'),
        ('penalty', 'Penalty'),
    ]

    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
    ]

    notification_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification_chama = models.ForeignKey(Chama, on_delete=models.CASCADE)
    notification_title = models.CharField(max_length=100, blank=True, null=True)
    notification_message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE)
    notification_priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default='normal')
    notification_sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="sent_notifications"
    )
    notification_is_read = models.BooleanField(default=False)
    notification_created_at = models.DateTimeField(auto_now_add=True)
    notification_updated_at = models.DateTimeField(auto_now=True)
    notification_related_meeting = models.ForeignKey(
        'Meeting',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="related_notifications"
    )
    notification_related_loan = models.ForeignKey(
        Loan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loan_notifications"
    )
    notification_related_contribution = models.ForeignKey(
        Contribution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contribution_notifications"
    )
    notification_related_penalty = models.ForeignKey(
        Penalty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="penalty_notifications"
    )

    def __str__(self):
        return f"{self.notification_type} - {self.notification_chama}"


class NotificationReply(models.Model):
    notification_reply_notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    notification_reply_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification_reply_message = models.TextField()
    notification_reply_created_at = models.DateTimeField(auto_now_add=True)
    notification_parent_reply = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE, related_name="thread_replies"
    )
    notification_reply_attachment = models.FileField(upload_to="notification_replies/", null=True, blank=True)

    def __str__(self):
        return f"Reply by {self.notification_reply_user}"


class NotificationDeliveryLog(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('sent', 'Sent'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )
    delivery_method = models.CharField(
        max_length=20,
        choices=[
            ('sms', 'SMS'),
            ('email', 'Email'),
            ('inapp', 'In-App'),
        ],
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.member} - {self.notification_status}"

class Meeting(models.Model):
    MEETING_TYPES = [
        ('physical', 'Physical'),
        ('online', 'Online'),
    ]
    MEETING_STATUS = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    meeting_chama = models.ForeignKey(Chama, on_delete=models.CASCADE, related_name="meetings")
    meeting_title = models.CharField(max_length=200)
    meeting_date = models.DateTimeField()
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPES, default='physical')
    meeting_venue = models.CharField(max_length=255, blank=True, null=True)
    meeting_online_link = models.URLField(blank=True, null=True)
    meeting_agenda = models.TextField()
    meeting_status = models.CharField(max_length=20, choices=MEETING_STATUS, default='scheduled')
    meeting_created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    meeting_created_at = models.DateTimeField(auto_now_add=True)
    meeting_updated_at = models.DateTimeField(auto_now=True)
    meeting_notification = models.OneToOneField(
        Notification, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="meeting_reminder"
    )

    def __str__(self):
        return self.meeting_title

    def clean(self):
        """Validation to ensure venue or link is provided depending on meeting type."""
        if self.meeting_type == "physical" and not self.meeting_venue:
            raise ValidationError("Venue is required for physical meetings.")
        if self.meeting_type == "online" and not self.meeting_online_link:
            raise ValidationError("Online link is required for online meetings.")

    # --- Helper properties for dashboard ---
    @property
    def total_present(self):
        return self.attendances.filter(attendance_status="present").count()

    @property
    def total_absent(self):
        return self.attendances.filter(attendance_status="absent").count()

    @property
    def total_excused(self):
        return self.attendances.filter(attendance_status="excused").count()

    @property
    def attendance_rate(self):
        total = self.attendances.count()
        return (self.total_present / total * 100) if total > 0 else 0

    class Meta:
        ordering = ["meeting_date"]


class MeetingAttendance(models.Model):
    ATTENDANCE_STATUS = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('excused', 'Excused'),
    ]

    attendance_meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="attendances")
    attendance_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meeting_attendances")
    attendance_status = models.CharField(max_length=10, choices=ATTENDANCE_STATUS, default='absent')
    attendance_timestamp = models.DateTimeField(auto_now_add=True)
    attendance_notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("attendance_meeting", "attendance_user")
        ordering = ["-attendance_timestamp"]

    def __str__(self):
        return f"{self.attendance_user} - {self.attendance_status}"

    # --- Helper methods ---
    def is_present(self):
        return self.attendance_status == "present"

    def is_absent(self):
        return self.attendance_status == "absent"

    def is_excused(self):
        return self.attendance_status == "excused"
