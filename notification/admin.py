from django.contrib import admin
from notification.models import (
    UserNotificationSettings,
    Notification,
    NotificationReply,
    NotificationDeliveryLog,
    Meeting,
    MeetingAttendance,
)

@admin.register(UserNotificationSettings)
class UserNotificationSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "user_notification_settings_user",
        "user_notification_settings_allow_sms",
        "user_notification_settings_allow_email",
        "user_notification_settings_allow_inapp",
        "user_notification_settings_fallback",
    )
    search_fields = ("user_notification_settings_user__username",)
    list_filter = (
        "user_notification_settings_allow_sms",
        "user_notification_settings_allow_email",
        "user_notification_settings_allow_inapp",
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "notification_title",
        "notification_type",
        "notification_priority",
        "notification_chama",
        "notification_sender",
        "notification_is_read",
        "notification_created_at",
    )
    list_filter = ("notification_type", "notification_priority", "notification_is_read")
    search_fields = ("notification_title", "notification_message", "notification_chama__chama_name")
    date_hierarchy = "notification_created_at"
    ordering = ("-notification_created_at",)


@admin.register(NotificationReply)
class NotificationReplyAdmin(admin.ModelAdmin):
    list_display = (
        "notification_reply_notification",
        "notification_reply_user",
        "notification_reply_message",
        "notification_reply_created_at",
    )
    search_fields = ("notification_reply_message", "notification_reply_user__username")
    date_hierarchy = "notification_reply_created_at"
    ordering = ("-notification_reply_created_at",)


@admin.register(NotificationDeliveryLog)
class NotificationDeliveryLogAdmin(admin.ModelAdmin):
    list_display = (
        "notification",
        "member",
        "notification_status",
        "delivery_method",
        "created_at",
        "updated_at",
    )
    list_filter = ("notification_status", "delivery_method")
    search_fields = ("notification__notification_title", "member__username")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = (
        "meeting_title",
        "meeting_chama",
        "meeting_date",
        "meeting_type",
        "meeting_status",
        "meeting_created_by",
        "meeting_created_at",
    )
    list_filter = ("meeting_type", "meeting_status")
    search_fields = ("meeting_title", "meeting_chama__chama_name")
    date_hierarchy = "meeting_date"
    ordering = ("-meeting_date",)


@admin.register(MeetingAttendance)
class MeetingAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "attendance_meeting",
        "attendance_user",
        "attendance_status",
        "attendance_timestamp",
    )
    list_filter = ("attendance_status",)
    search_fields = ("attendance_meeting__meeting_title", "attendance_user__username")
    date_hierarchy = "attendance_timestamp"
    ordering = ("-attendance_timestamp",)
