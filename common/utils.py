from django.core.paginator import Paginator
from notification.models import Notification, NotificationDeliveryLog

# -------------------------
# Generic helpers
# -------------------------

def set_active_chama(request, chama_id):
    """Save active chama ID in session."""
    request.session["active_chama_id"] = chama_id

def paginate_queryset(queryset, page_number, per_page=20):
    """Reusable pagination helper."""
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(page_number)

def update_status(obj, field, value):
    """Generic status update helper."""
    setattr(obj, field, value)
    obj.save()
    return obj

def create_child_record(model, parent_field, parent, user_field, user, **kwargs):
    """Generic helper for child records (reply, attendance, comment)."""
    payload = {parent_field: parent, user_field: user}
    payload.update(kwargs)
    return model.objects.create(**payload)

def send_to_members(members, create_fn):
    """Loop through members and apply a function that returns a created object."""
    results = []
    for member in members:
        obj = create_fn(member)
        if obj:
            results.append(obj)
    return results

# -------------------------
# Finance + Dashboard unified notification helper
# -------------------------

def send_chama_notification(
    chama,
    recipients,
    title,
    message,
    sender=None,
    n_type="announcement",
    priority="normal",
    related_contribution=None,
    related_loan=None,
    related_penalty=None,
    related_meeting=None
):
    """
    Create Notification records for a list of users and a delivery log entry.
    Works for finance (contributions, loans, penalties) and dashboard (meetings, reminders).
    
    Args:
        chama: Chama instance
        recipients: iterable of User objects
        title: notification title
        message: notification message
        sender: User instance (optional)
        n_type: notification type (e.g., 'announcement', 'payment', 'loan', 'meeting', 'penalty')
        priority: 'normal' or 'high'
        related_*: optional related objects (Contribution, Loan, Penalty, Meeting)
    """
    created_notifications = []
    for user in recipients:
        try:
            notif = Notification.objects.create(
                notification_user=user,
                notification_chama=chama,
                notification_title=title,
                notification_message=message,
                notification_type=n_type,
                notification_priority=priority,
                notification_sender=sender
            )
            # Attach related objects if provided
            if related_contribution:
                notif.notification_related_contribution = related_contribution
            if related_loan:
                notif.notification_related_loan = related_loan
            if related_penalty:
                notif.notification_related_penalty = related_penalty
            if related_meeting:
                notif.notification_related_meeting = related_meeting
            notif.save()

            # Create a delivery log (in-app by default)
            NotificationDeliveryLog.objects.create(
                notification=notif,
                member=user,
                notification_status="sent",
                delivery_method="inapp"
            )
            created_notifications.append(notif)
        except Exception:
            # Fail silently for individual users (you might want to log errors)
            continue
    return created_notifications

