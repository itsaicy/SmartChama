from django.urls import path
from notification import views
from notification.meeting_views import (
    meeting_detail, meeting_list, delete_meeting,
    create_meeting, update_meeting, admin_meeting_list,
    my_attendance, confirm_attendance
)

app_name = "notification"

urlpatterns = [
    # Notifications
    path("", views.NotificationListView.as_view(), name="notification_list"),
    path("chama/<int:chama_id>/", views.NotificationListView.as_view(), name="chama_notifications"),
    path("detail/<int:pk>/", views.NotificationDetailView.as_view(), name="notification_detail"),
    path("create/<int:chama_id>/", views.create_notification, name="create_notification"),
    path("reply/<int:id>/", views.notification_reply, name="notification_reply"),
    path("logs/", views.NotificationLogsView.as_view(), name="notification_logs"),
    path("resend/<int:id>/", views.resend_notification, name="resend_notification"),
    path("settings/", views.notification_settings, name="notification_settings"),
    path("edit/<int:pk>/", views.NotificationUpdateView.as_view(), name="edit_notification"),
    path("delete/<int:pk>/", views.NotificationDeleteView.as_view(), name="delete_notification"),
    path("mark/<int:id>/", views.mark_as_read, name="mark_as_read"),

    # Meetings
    path("meetings/", meeting_list, name="meeting_list"),
    path("meetings/<int:pk>/", meeting_detail, name="meeting_detail"),
    path("attendance/my/", my_attendance, name="my_attendance"),
    path("official/meetings/", admin_meeting_list, name="admin_meeting_list"),
    path("official/meetings/create/", create_meeting, name="create_meeting"),
    path("official/meetings/<int:pk>/edit/", update_meeting, name="update_meeting"),
    path("official/meetings/<int:pk>/delete/", delete_meeting, name="delete_meeting"),
    path("meetings/<int:pk>/confirm/<str:status>/", confirm_attendance, name="confirm_attendance"),
]
