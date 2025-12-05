from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.generic import DetailView
from .models import Notification, NotificationReply, NotificationDeliveryLog, UserNotificationSettings
from chama.models import Chama, Membership
from notification.forms import NotificationForm

from common.utils import (
    set_active_chama, paginate_queryset, update_status,
    create_child_record, send_to_members
)
from common.mixins import (
    PaginatedListMixin, SenderScopedDeleteView,
    SenderScopedUpdateView
)

# -----------------------------------------------------
# 0. SELECT CHAMA
# -----------------------------------------------------
@login_required
def select_chama(request, chama_id):
    set_active_chama(request, chama_id)
    return redirect("notification:chama_notifications", chama_id=chama_id)

# -----------------------------------------------------
# 1. NOTIFICATION LIST
# -----------------------------------------------------
class NotificationListView(PaginatedListMixin):
    model = Notification
    template_name = "notification/notification_list.html"
    context_object_name = "notifications"

    def get_queryset(self):
        qs = Notification.objects.filter(
            notification_user=self.request.user
        ).select_related("notification_sender", "notification_chama").order_by("-notification_created_at")

        chama_id = self.kwargs.get("chama_id")
        if chama_id:
            qs = qs.filter(notification_chama_id=chama_id)

        filter_type = self.request.GET.get("type", "all")
        if filter_type == "announcements":
            qs = qs.filter(notification_type="announcement")
        elif filter_type == "targeted":
            qs = qs.exclude(notification_type="announcement")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        ctx["filter_type"] = self.request.GET.get("type", "all")
        ctx["unread_count"] = qs.filter(notification_is_read=False).count()
        ctx["active_chama"] = self.kwargs.get("chama_id")
        return ctx

# -----------------------------------------------------
# 2. DETAIL PAGE
# -----------------------------------------------------
class NotificationDetailView(DetailView):
    model = Notification
    template_name = "notification/notification_detail.html"
    context_object_name = "notification"

    def get_queryset(self):
        return Notification.objects.filter(notification_user=self.request.user)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not obj.notification_is_read:
            obj.notification_is_read = True
            obj.save()
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["replies"] = NotificationReply.objects.filter(
            notification_reply_notification=self.object
        ).select_related("notification_reply_user")
        return ctx

# -----------------------------------------------------
# 3. REPLY TO A NOTIFICATION
# -----------------------------------------------------
@login_required
@require_POST
def notification_reply(request, id):
    notification = get_object_or_404(Notification, id=id, notification_user=request.user)
    msg = request.POST.get("reply_message")
    if msg:
        create_child_record(
            model=NotificationReply,
            parent_field="notification_reply_notification",
            parent=notification,
            user_field="notification_reply_user",
            user=request.user,
            notification_reply_message=msg
        )
        messages.success(request, "Reply sent!")
    return redirect("notification:notification_detail", id=id)

# -----------------------------------------------------
# 4. CREATE NOTIFICATION
# -----------------------------------------------------
@login_required
def create_notification(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)

    if request.method == "POST":
        form = NotificationForm(request.POST)
        target_members = request.POST.getlist("target_members")

        if form.is_valid():
            cd = form.cleaned_data
            if target_members:
                memberships = Membership.objects.filter(
                    id__in=target_members, membership_chama=chama
                ).select_related("membership_user")
            else:
                memberships = Membership.objects.filter(
                    membership_chama=chama
                ).select_related("membership_user")

            def create_for_member(member):
                notif = Notification.objects.create(
                    notification_user=member.membership_user,
                    notification_chama=chama,
                    notification_title=cd["notification_title"],
                    notification_message=cd["notification_message"],
                    notification_type=cd["notification_type"],
                    notification_priority=cd["notification_priority"],
                    notification_sender=request.user
                )
                NotificationDeliveryLog.objects.create(
                    notification=notif,
                    member=member.membership_user,
                    delivery_method="inapp",
                    notification_status="sent"
                )
                return notif

            send_to_members(memberships, create_for_member)
            messages.success(request, f"Notification sent to {memberships.count()} members!")
            return redirect("notification:chama_notifications", chama_id=chama.id)
    else:
        form = NotificationForm()

    members = Membership.objects.filter(membership_chama=chama).select_related("membership_user")
    return render(request, "notification/create_notification.html", {
        "chama": chama,
        "members": members,
        "form": form
    })

# -----------------------------------------------------
# 5. SETTINGS
# -----------------------------------------------------
@login_required
def notification_settings(request):
    settings_obj, _ = UserNotificationSettings.objects.get_or_create(
        user_notification_settings_user=request.user
    )

    if request.method == "POST":
        settings_obj.user_notification_settings_allow_email = request.POST.get("allow_email") == "on"
        settings_obj.user_notification_settings_allow_sms = request.POST.get("allow_sms") == "on"
        settings_obj.user_notification_settings_allow_inapp = request.POST.get("allow_inapp") == "on"
        settings_obj.save()
        messages.success(request, "Settings updated.")
        return redirect("notification:notification_settings")

    return render(request, "notification/notification_settings.html", {"settings": settings_obj})

# -----------------------------------------------------
# 6. DELIVERY LOGS
# -----------------------------------------------------
class NotificationLogsView(PaginatedListMixin):
    model = NotificationDeliveryLog
    template_name = "notification/notification_logs.html"
    context_object_name = "logs"

    def get_queryset(self):
        status_filter = self.request.GET.get("status", "all")
        notification_id = self.request.GET.get("notification")

        qs = NotificationDeliveryLog.objects.filter(
            notification__notification_sender=self.request.user
        ).select_related("notification", "member").order_by("-created_at")

        if notification_id:
            qs = qs.filter(notification_id=notification_id)
        if status_filter != "all":
            qs = qs.filter(notification_status=status_filter)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_filter"] = self.request.GET.get("status", "all")
        return ctx

# -----------------------------------------------------
# 7. RESEND
# -----------------------------------------------------
@login_required
@require_POST
def resend_notification(request, id):
    log = get_object_or_404(NotificationDeliveryLog, id=id, notification__notification_sender=request.user)
    update_status(log, "notification_status", "pending")
    messages.success(request, "Notification queued for resend.")
    return redirect("notification:notification_logs")

# -----------------------------------------------------
# 8. DELETE NOTIFICATION
# -----------------------------------------------------
class NotificationDeleteView(SenderScopedDeleteView):
    model = Notification
    template_name = "notification/confirm_delete.html"

    def get_success_url(self):
        return self.request.GET.get("next") or "/notifications/"

# -----------------------------------------------------
# 9. EDIT NOTIFICATION
# -----------------------------------------------------
class NotificationUpdateView(SenderScopedUpdateView):
    model = Notification
    form_class = NotificationForm
    template_name = "notification/edit_notification.html"

    def form_valid(self, form):
        messages.success(self.request, "Notification updated!")
        return super().form_valid(form)

# -----------------------------------------------------
# 10. MARK AS READ
# -----------------------------------------------------
@login_required
def mark_as_read(request, id):
    notification = get_object_or_404(Notification, id=id, notification_user=request.user)
    if not notification.notification_is_read:
        update_status(notification, "notification_is_read", True)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "ok", "id": id})

    messages.success(request, "Notification marked as read.")
    return redirect("notification:notification_detail", id=id)
