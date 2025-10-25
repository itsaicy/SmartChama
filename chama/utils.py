from chama.models import Membership

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
    Returns the dashboard name (URL pattern) based on the user's active role.
    If user belongs to multiple chamas, picks the first active one.
    """

    membership = Membership.objects.filter(
        membership_user=user,
        membership_status='active'
    ).first()

    if membership:
        role = membership.membership_role
        if role == 'admin':
            return 'admin_dashboard'
        elif role == 'secretary':
            return 'secretary_dashboard'
        elif role == 'treasurer':
            return 'treasurer_dashboard'
        else:
            return 'member_dashboard'
    return 'member_dashboard'  # Default fallback
