from chama.models import Membership
from django.urls import reverse

def is_chama_admin(user, chama):
    return Membership.objects.filter(
        membership_user=user,
        membership_chama=chama,
        membership_role='admin'
    ).exists()

def is_chama_secretary(user, chama):
    return Membership.objects.filter(
        membership_user=user,
        membership_chama=chama,
        membership_role='secretary'
    ).exists()

def is_admin_or_secretary(user, chama):
    return is_chama_admin(user, chama) or is_chama_secretary(user, chama)

def get_user_dashboard_redirect(user):
    """
    Returns the dashboard URL based on the user's active role.
    If user belongs to multiple chamas, picks the first active one.
    """

    membership = Membership.objects.filter(
        membership_user=user,
        membership_status='active'
    ).first()

    if membership:
        role = membership.membership_role
        chama_id = membership.membership_chama.pk

        if role == 'admin':
            return reverse("dashboard:admin_dashboard", kwargs={"chama_id": chama_id})
        elif role == 'secretary':
            return reverse("dashboard:secretary_dashboard", kwargs={"chama_id": chama_id})
        elif role == 'treasurer':
            return reverse("dashboard:treasurer_dashboard", kwargs={"chama_id": chama_id})
        else:
            return reverse("dashboard:member_dashboard", kwargs={"chama_id": chama_id})

    return reverse("dashboard:member_dashboard", kwargs={"chama_id": 0})

def get_active_chama(request):
    """
    Returns the active chama for the logged-in user based on session or first active membership.
    """
    chama_id = request.session.get("active_chama_id")

    if chama_id:
        try:
            from chama.models import Chama
            return Chama.objects.get(id=chama_id)
        except Chama.DoesNotExist:
            return None

    # Fallback: use first active membership
    membership = Membership.objects.filter(
        membership_user=request.user,
        membership_status="active"
    ).first()

    if membership:
        return membership.membership_chama

    return None
