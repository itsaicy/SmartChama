from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, UpdateView, DeleteView, ListView
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.db.models import Q
from django.urls import reverse_lazy

from .models import Notification, NotificationReply, NotificationDeliveryLog, UserNotificationSettings
from chama.models import Chama, Membership
from notification.forms import NotificationForm

# Handle the mixin import gracefully
try:
    from common.mixins import PaginatedListMixin
except ImportError:
    class PaginatedListMixin:
        paginate_by = 10

# -----------------------------------------------------
# 1. NOTIFICATION LIST (With your Filter Logic)
# -----------------------------------------------------
class NotificationListView(PaginatedListMixin, ListView):
    model = Notification
    template_name = "notification/notification_list.html"
    context_object_name = "notifications"

    def get_queryset(self):
        qs = Notification.objects.filter(
            notification_user=self.request.user
        ).select_related("notification_sender", "notification_chama").order_by("-notification_created_at")

        # --- FILTERING LOGIC ---
        url_chama_id = self.kwargs.get("chama_id")
        get_chama_id = self.request.GET.get("chama")
        session_chama_id = self.request.session.get('active_chama_id')

        if url_chama_id:
            qs = qs.filter(notification_chama_id=url_chama_id)
        elif get_chama_id is not None:
            if get_chama_id:
                qs = qs.filter(notification_chama_id=get_chama_id)
        elif session_chama_id:
            qs = qs.filter(notification_chama_id=session_chama_id)

        # --- TYPE FILTERING ---
        filter_type = self.request.GET.get("type", "all")
        if filter_type == "announcements":
            qs = qs.filter(notification_type="announcement")
        elif filter_type == "targeted":
            qs = qs.exclude(notification_type="announcement")
            
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_type"] = self.request.GET.get("type", "all")
        
        active_id = (
            self.kwargs.get("chama_id") or 
            self.request.GET.get("chama") or 
            self.request.session.get('active_chama_id')
        )
        ctx["active_chama"] = active_id
        
        user_memberships = Membership.objects.filter(
            membership_user=self.request.user, 
            membership_status='active'
        ).select_related('membership_chama')
        ctx["user_chamas"] = [m.membership_chama for m in user_memberships]
        
        return ctx

# -----------------------------------------------------
# 2. DETAIL PAGE
# -----------------------------------------------------
class NotificationDetailView(DetailView):
    model = Notification
    template_name = "notification/notification_detail.html"
    context_object_name = "notification"

    def get_queryset(self):
        # Security: User must be the recipient (notification_user) or the sender
        return Notification.objects.filter(
            Q(notification_user=self.request.user) | Q(notification_sender=self.request.user)
        )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        # Mark as read if the viewer is the recipient
        if obj.notification_user == self.request.user and not obj.notification_is_read:
            obj.notification_is_read = True
            obj.save()
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["replies"] = NotificationReply.objects.filter(
            notification_reply_notification=self.object
        ).select_related("notification_reply_user").order_by('notification_reply_created_at')
        
        ctx["allow_replies"] = self.object.notification_type not in ['announcement', 'reminder']
        return ctx

# -----------------------------------------------------
# 3. REPLY ACTION (+ New Notification Logic)
# -----------------------------------------------------
@login_required
@require_POST
def notification_reply(request, id):
    notification = get_object_or_404(Notification, id=id)
    
    # Permission check: must be sender or recipient
    if request.user != notification.notification_user and request.user != notification.notification_sender:
         messages.error(request, "Unauthorized.")
         return redirect("notification:notification_list")

    if notification.notification_type in ['announcement', 'reminder']:
        messages.error(request, "Replies are disabled for this notification.")
        return redirect("notification:notification_detail", pk=id)

    msg = request.POST.get("reply_message")
    if msg:
        # 1. Create the Reply
        NotificationReply.objects.create(
            notification_reply_notification=notification,
            notification_reply_user=request.user,
            notification_reply_message=msg
        )

        # 2. Notify the *other* person (The "So and so replied" feature)
        # If I am the recipient replying, notify the sender
        if request.user == notification.notification_user and notification.notification_sender:
            Notification.objects.create(
                notification_user=notification.notification_sender, # Target
                notification_sender=request.user,                   # Source
                notification_chama=notification.notification_chama,
                notification_title="New Reply",
                notification_message=f"{request.user.username} replied to: {notification.notification_title}",
                notification_type='reply',
                notification_priority='normal'
            )
        # If I am the sender replying, notify the recipient
        elif request.user == notification.notification_sender and notification.notification_user:
            Notification.objects.create(
                notification_user=notification.notification_user,   # Target
                notification_sender=request.user,                   # Source
                notification_chama=notification.notification_chama,
                notification_title="New Reply",
                notification_message=f"{request.user.username} replied to the notification.",
                notification_type='reply',
                notification_priority='normal'
            )

        messages.success(request, "Reply sent.")
    
    return redirect("notification:notification_detail", pk=id)

# -----------------------------------------------------
# 4. CREATE NOTIFICATION
# -----------------------------------------------------
@login_required
def create_notification(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    user_membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)
    
    if user_membership.membership_role not in ['admin', 'chairman', 'secretary', 'treasurer']:
        messages.error(request, "Only officials can create notifications.")
        return redirect('notification:chama_notifications', chama_id=chama.id)

    if request.method == "POST":
        form = NotificationForm(request.POST)
        target_ids = request.POST.getlist("target_members")
        select_all = request.POST.get("select_all_members")

        if form.is_valid():
            data = form.cleaned_data
            
            if select_all:
                memberships = Membership.objects.filter(membership_chama=chama, membership_status='active')
            else:
                memberships = Membership.objects.filter(id__in=target_ids, membership_chama=chama)

            count = 0
            for membership in memberships:
                recipient = membership.membership_user
                settings, _ = UserNotificationSettings.objects.get_or_create(user_notification_settings_user=recipient)

                if settings.user_notification_settings_allow_inapp or settings.user_notification_settings_fallback:
                    notif = Notification.objects.create(
                        notification_user=recipient,
                        notification_chama=chama,
                        notification_title=data['notification_title'],
                        notification_message=data['notification_message'],
                        notification_type=data['notification_type'],
                        notification_priority=data['notification_priority'],
                        notification_sender=request.user
                    )
                    NotificationDeliveryLog.objects.create(
                        notification=notif, member=recipient,
                        delivery_method='inapp', notification_status='sent'
                    )
                count += 1

            messages.success(request, f"Sent to {count} members.")
            return redirect("notification:chama_notifications", chama_id=chama.id)
    else:
        form = NotificationForm()

    members = Membership.objects.filter(membership_chama=chama, membership_status='active')
    return render(request, "notification/create_notification.html", {
        "chama": chama, "members": members, "form": form
    })

# -----------------------------------------------------
# 5. SETTINGS
# -----------------------------------------------------
@login_required
def notification_settings(request):
    settings_obj, _ = UserNotificationSettings.objects.get_or_create(user_notification_settings_user=request.user)

    if request.method == "POST":
        settings_obj.user_notification_settings_allow_email = request.POST.get("allow_email") == "on"
        settings_obj.user_notification_settings_allow_sms = request.POST.get("allow_sms") == "on"
        settings_obj.user_notification_settings_allow_inapp = request.POST.get("allow_inapp") == "on"
        settings_obj.save()
        messages.success(request, "Notification preferences saved.")
        return redirect("notification:notification_settings")

    return render(request, "notification/notification_settings.html", {"settings": settings_obj})

# -----------------------------------------------------
# 6. LOGS
# -----------------------------------------------------
class NotificationLogsView(PaginatedListMixin, ListView):
    model = NotificationDeliveryLog
    template_name = "notification/notification_logs.html"
    context_object_name = "logs"

    def get_queryset(self):
        status = self.request.GET.get("status", "all")
        qs = NotificationDeliveryLog.objects.filter(
            notification__notification_sender=self.request.user
        ).select_related("notification", "member").order_by("-created_at")

        if status != "all":
            qs = qs.filter(notification_status=status)
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
    log.notification_status = 'pending'
    log.save()
    messages.success(request, "Notification queued for resend.")
    return redirect("notification:notification_logs")

# -----------------------------------------------------
# 8. UPDATE & DELETE NOTIFICATION (Generic)
# -----------------------------------------------------
class NotificationUpdateView(UpdateView):
    model = Notification
    form_class = NotificationForm
    template_name = "notification/edit_notification.html"

    def get_queryset(self):
        return Notification.objects.filter(notification_sender=self.request.user)

    def get_success_url(self):
        messages.success(self.request, "Notification updated successfully!")
        return reverse_lazy("notification:notification_detail", kwargs={"pk": self.object.id})

class NotificationDeleteView(DeleteView):
    model = Notification
    template_name = "notification/confirm_delete.html"
    success_url = reverse_lazy("notification:notification_list")

    def get_queryset(self):
        return Notification.objects.filter(notification_sender=self.request.user)
        
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Notification deleted.")
        return super().delete(request, *args, **kwargs)

# -----------------------------------------------------
# 9. MARK AS READ
# -----------------------------------------------------
@login_required
def mark_as_read(request, id):
    notification = get_object_or_404(Notification, id=id, notification_user=request.user)
    if not notification.notification_is_read:
        notification.notification_is_read = True
        notification.save()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'id': id})
        
    messages.success(request, "Marked as read.")
    return redirect("notification:notification_list")

# -----------------------------------------------------
# 10. EDIT REPLY (AJAX - "Small Tab")
# -----------------------------------------------------
@login_required
@require_POST
def save_reply_edit(request, reply_id):
    """
    AJAX view to save an edited reply inline.
    """
    reply = get_object_or_404(NotificationReply, id=reply_id)
    
    # Security: Only author can edit
    if reply.notification_reply_user != request.user:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    new_content = request.POST.get('content')
    if new_content:
        reply.notification_reply_message = new_content
        reply.save()
        return JsonResponse({
            'status': 'success', 
            'content': reply.notification_reply_message,
            'message': 'Reply updated.'
        })
    
    return JsonResponse({'status': 'error', 'message': 'Content cannot be empty'}, status=400)

# -----------------------------------------------------
# 11. DELETE REPLY
# -----------------------------------------------------
@login_required
def delete_reply(request, reply_id):
    reply = get_object_or_404(NotificationReply, id=reply_id)
    
    # Security: Only author can delete
    if reply.notification_reply_user != request.user:
        messages.error(request, "Unauthorized action.")
        return redirect("notification:notification_detail", pk=reply.notification_reply_notification.id)

    notification_id = reply.notification_reply_notification.id
    reply.delete()
    messages.success(request, "Reply deleted.")
    return redirect("notification:notification_detail", pk=notification_id)