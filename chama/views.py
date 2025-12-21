from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import EmailMessage
from chama.models import Chama, Membership, JoinRequest
from notification.models import Notification
from user.models import User
from chama.forms import ChamaForm, ChamaPaymentForm
from chama.utils import is_chama_admin, is_chama_secretary, is_admin_or_secretary
from user.views import activateEmail
from user.tokens import account_activation_token

app_name = 'chama'

# ==========================================
#           STANDARD CHAMA VIEWS
# ==========================================

@login_required(login_url="login")
def chama_list(request):
    """Show all available chamas except those the user is already in or has requested to join."""
    user_memberships = Membership.objects.filter(
        membership_user=request.user,
        membership_status='active'
    ).values_list('membership_chama_id', flat=True)

    user_join_requests = JoinRequest.objects.filter(
        join_request_user=request.user,
        join_request_status='pending'
    ).values_list('join_request_chama_id', flat=True)

    chamas = Chama.objects.exclude(
        id__in=user_memberships
    ).exclude(
        id__in=user_join_requests
    ).order_by('-chama_created_at')

    context = {
        'chamas': chamas,
        'user_join_requests': user_join_requests,
    }
    return render(request, 'chama/chama_list.html', context)


@login_required(login_url="login")
def create_chama(request):
    payment_form = ChamaPaymentForm()
    if request.method == 'POST':
        form = ChamaForm(request.POST)
        if form.is_valid():
            chama = form.save(commit=False)
            chama.chama_created_by = request.user
            chama.save()
            Membership.objects.create(
                membership_user=request.user,
                membership_chama=chama,
                membership_role='admin'
            )
            messages.success(request, f"Chama '{chama.chama_name}' created successfully!")
            return redirect('chama:chama_detail', pk=chama.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ChamaForm()

    return render(request, 'chama/create_chama.html', {
        'form': form,
        'payment_form': payment_form,
    })


@login_required(login_url='login')
def chama_detail(request, pk):
    chama = get_object_or_404(Chama, pk=pk)
    members = Membership.objects.filter(membership_chama=chama).select_related('membership_user')
    current_members = members.count()
    max_members = chama.chama_max_members
    remaining_slots = max_members - current_members
    
    is_admin = is_chama_admin(request.user, chama)
    is_secretary = is_chama_secretary(request.user, chama)
    is_member = members.filter(membership_user=request.user).exists()
    
    # Check for pending request for THIS specific user
    has_pending_request = JoinRequest.objects.filter(
        join_request_user=request.user,
        join_request_chama=chama,
        join_request_status='pending'
    ).exists()
    
    join_requests = []
    if is_admin or is_secretary:
        join_requests = JoinRequest.objects.filter(
            join_request_chama=chama, join_request_status='pending'
        )

    context = {
        'chama': chama,
        'members': members,
        'join_requests': join_requests,
        'is_admin': is_admin,
        'is_secretary': is_secretary,
        'is_member': is_member,
        'current_members': current_members,
        'max_members': max_members,
        'remaining_slots': remaining_slots,
        'has_pending_request': has_pending_request,
    }
    return render(request, 'chama/chama_detail.html', context)


@login_required(login_url='login')
def edit_chama(request, pk):
    chama = get_object_or_404(Chama, pk=pk)
    if not is_admin_or_secretary(request.user, chama):
        messages.error(request, "You don't have permission to edit this chama.")
        return redirect('chama:chama_detail', pk=chama.pk)

    if request.method == 'POST':
        form = ChamaForm(request.POST, instance=chama)
        if form.is_valid():
            chama = form.save()
            
            # Send Notification to all members about the update
            members = Membership.objects.filter(membership_chama=chama, membership_status='active')
            for member in members:
                # Avoid notifying the person who made the edit
                if member.membership_user != request.user:
                    Notification.objects.create(
                        notification_user=member.membership_user,
                        notification_chama=chama,
                        notification_title="Chama Details Updated",
                        notification_message=f"Chama details have been updated by {request.user.get_full_name()}.",
                        notification_type="announcement",
                        notification_sender=request.user
                    )

            messages.success(request, "Chama details updated successfully.")
            return redirect('chama:chama_detail', pk=chama.pk)
    else:
        form = ChamaForm(instance=chama)
    return render(request, 'chama/create_chama.html', {'form': form, 'edit_mode': True})


@login_required(login_url='login')
def my_chamas(request):
    memberships = Membership.objects.select_related('membership_chama').filter(
        membership_user=request.user,
        membership_status='active'
    )
    chamas = [m.membership_chama for m in memberships]

    for chama in chamas:
        chama.all_members = Membership.objects.filter(
            membership_chama=chama
        ).select_related('membership_user')
        chama.member_count = chama.all_members.count()
        chama.max_members = chama.chama_max_members

    context = {
        "chamas": chamas,
        "memberships": memberships
    }
    return render(request, "chama/my_chamas.html", context)


@login_required(login_url='login')
def join_chama(request, pk):
    chama = get_object_or_404(Chama, pk=pk)

    # 1. Validation
    if Membership.objects.filter(membership_user=request.user, membership_chama=chama).exists():
        messages.info(request, "You are already a member.")
        return redirect('chama:chama_detail', pk=chama.pk)

    if JoinRequest.objects.filter(join_request_user=request.user, join_request_chama=chama, join_request_status='pending').exists():
        messages.warning(request, "Request already sent.")
        return redirect('chama:chama_detail', pk=chama.pk)

    # 2. Create Request
    JoinRequest.objects.create(join_request_user=request.user, join_request_chama=chama)

    # 3. Notify Admins and Secretaries
    officials = Membership.objects.filter(
        membership_chama=chama, 
        membership_role__in=['admin', 'secretary']
    )
    
    for official in officials:
        Notification.objects.create(
            notification_user=official.membership_user,
            notification_chama=chama,
            notification_title="New Join Request",
            notification_message=f"{request.user.get_full_name()} wants to join {chama.chama_name}.",
            notification_type="announcement",
            notification_sender=request.user
        )

    # 4. Feedback to Requester
    messages.success(request, "Your join request has been sent.")
    return redirect('chama:chama_detail', pk=chama.pk)


@login_required
def accept_request(request, request_id):
    join_request = get_object_or_404(JoinRequest, id=request_id)
    chama = join_request.join_request_chama
    
    # Permission Check
    if not is_admin_or_secretary(request.user, chama):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    # 1. Update Join Request
    join_request.join_request_status = "accepted"
    join_request.join_request_reviewed_by = request.user
    join_request.join_request_reviewed_at = timezone.now()
    join_request.save()
    
    # 2. Create Membership (Add to DB)
    Membership.objects.create(
        membership_user=join_request.join_request_user,
        membership_chama=chama,
        membership_role="member",
        membership_status="active"
    )

    # 3. Notify the New Member
    Notification.objects.create(
        notification_user=join_request.join_request_user,
        notification_chama=chama,
        notification_title="Request Accepted",
        notification_message=f"Welcome! Your request to join {chama.chama_name} has been accepted.",
        notification_type="member_joined",
        notification_sender=request.user
    )

    messages.success(request, f"{join_request.join_request_user.user_first_name} added to the group.")
    return JsonResponse({'success': True, 'message': 'Request accepted'})


@login_required
def reject_request(request, request_id):
    join_request = get_object_or_404(JoinRequest, id=request_id)
    chama = join_request.join_request_chama
    
    if not is_admin_or_secretary(request.user, chama):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    # 1. Update Join Request
    join_request.join_request_status = "rejected"
    join_request.join_request_reviewed_by = request.user
    join_request.join_request_reviewed_at = timezone.now()
    join_request.save()

    # 2. Notify the Rejected User
    Notification.objects.create(
        notification_user=join_request.join_request_user,
        notification_chama=chama,
        notification_title="Request Rejected",
        notification_message=f"Your request to join {chama.chama_name} was declined.",
        notification_type="announcement",
        notification_sender=request.user
    )

    messages.success(request, "Request rejected.")
    return JsonResponse({'success': True, 'message': 'Request rejected'})


@login_required(login_url='login')
def join_requests(request, pk):
    """Show all pending join requests for a chama (admin/secretary only)."""
    chama = get_object_or_404(Chama, pk=pk)
    if not is_admin_or_secretary(request.user, chama):
        return HttpResponseForbidden("Unauthorized")

    pending_requests = JoinRequest.objects.filter(
        join_request_chama=chama,
        join_request_status='pending'
    ).select_related('join_request_user')
    
    history_requests = JoinRequest.objects.filter(
        join_request_chama=chama
    ).exclude(join_request_status='pending').select_related('join_request_user').order_by('-join_request_reviewed_at')

    context = {
        'chama': chama,
        'join_requests': pending_requests,
        'pending_requests': pending_requests,
        'history_requests': history_requests,
    }
    return render(request, 'chama/join_requests.html', context)


# ==========================================
#           MEMBER MANAGEMENT LOGIC
# ==========================================

@login_required(login_url='login')
def manage_members(request, pk):
    """Manage members for a chama (admin/secretary only)."""
    chama = get_object_or_404(Chama, pk=pk)
    if not is_admin_or_secretary(request.user, chama):
        return HttpResponseForbidden("Unauthorized")

    members = Membership.objects.filter(membership_chama=chama).select_related('membership_user')
    is_admin = is_chama_admin(request.user, chama)

    context = {
        'chama': chama,
        'members': members,
        'is_admin': is_admin,
    }
    return render(request, 'chama/manage_members.html', context)


@login_required
def add_member_to_chama(request, chama_id):
    """
    Handles adding a member. 
    1. If User exists: Adds them to Chama immediately.
    2. If User does not exist: Creates User (Inactive), sends email confirmation with TEMP PASSWORD, adds to Chama.
    """
    chama = get_object_or_404(Chama, id=chama_id)
    
    # Check permissions
    if not is_admin_or_secretary(request.user, chama):
        messages.error(request, "Unauthorized action.")
        return redirect("chama:manage_members", pk=chama_id)

    if request.method == "POST":
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        email = request.POST.get("email")
        phone = request.POST.get("phone_number")
        national_id = request.POST.get("national_id")

        # Check if user already exists in the system
        existing_user = User.objects.filter(user_email=email).first()

        if existing_user:
            # ==================================================
            # CASE 1: USER IS ALREADY REGISTERED
            # We just add them to the Chama. No password needed.
            # ==================================================
            if Membership.objects.filter(membership_user=existing_user, membership_chama=chama).exists():
                messages.warning(request, "User is already a member of this chama.")
            else:
                Membership.objects.create(
                    membership_user=existing_user,
                    membership_chama=chama,
                    membership_role='member',
                    membership_status='active'
                )
                
                # Send In-App Notification
                Notification.objects.create(
                    notification_user=existing_user,
                    notification_chama=chama,
                    notification_title="Added to Chama",
                    notification_message=f"You have been added to {chama.chama_name} by {request.user.get_full_name()}.",
                    notification_type="member_joined",
                    notification_sender=request.user
                )
                
                # Send simple email
                mail_subject = f'Added to {chama.chama_name}'
                message = f"Hi {existing_user.user_first_name},\n\nYou have been added to the chama '{chama.chama_name}'. Log in to your dashboard to view details."
                email_msg = EmailMessage(mail_subject, message, to=[email])
                email_msg.send()

                messages.success(request, f"{existing_user.get_full_name()} added successfully.")
        
        else:
            # ==================================================
            # CASE 2: NEW USER (NOT REGISTERED)
            # ==================================================
            try:
                # 1. Generate Random Password
                random_password = get_random_string(length=12)

                # 2. Create the User (Inactive until they confirm email)
                new_user = User.objects.create_user(
                    user_email=email,
                    user_first_name=first_name,
                    user_last_name=last_name,
                    user_phone_number=phone,
                    user_national_id=national_id,
                    password=random_password
                )
                new_user.is_active = False 
                new_user.save()

                # 3. Add to Chama
                Membership.objects.create(
                    membership_user=new_user,
                    membership_chama=chama,
                    membership_role='member',
                    membership_status='active'
                )

                # 4. Construct Email WITH PASSWORD
                current_site = get_current_site(request)
                uid = urlsafe_base64_encode(force_bytes(new_user.pk))
                token = account_activation_token.make_token(new_user)
                activation_link = f"http://{current_site.domain}/activate/{uid}/{token}/"

                mail_subject = f'Welcome to {chama.chama_name} - Login Details'
                
                message = f"""
                Hi {first_name},

                You have been added to the chama '{chama.chama_name}'.
                
                Your account has been created. Here are your login details:

                ------------------------------------------------
                Email: {email}
                Temporary Password: {random_password}
                ------------------------------------------------

                Step 1: Click this link to activate your account:
                {activation_link}

                Step 2: Log in using the temporary password above.

                Step 3: Go to your Profile and change your password immediately.
                
                Welcome!
                """

                email_msg = EmailMessage(mail_subject, message, to=[email])
                email_msg.send()

                messages.success(request, f"Account created for {first_name}. An email with the temporary password has been sent.")

            except Exception as e:
                print(f"Error creating user: {e}") 
                messages.error(request, f"Error creating user: {str(e)}")

    return redirect("chama:manage_members", pk=chama_id)


@login_required
def edit_member_details(request, chama_id):
    """
    Updates member details (First Name, Last Name, Phone) from the Modal.
    """
    chama = get_object_or_404(Chama, id=chama_id)
    
    if not is_admin_or_secretary(request.user, chama):
        messages.error(request, "Unauthorized.")
        return redirect("chama:manage_members", pk=chama_id)

    if request.method == "POST":
        target_user_id = request.POST.get("user_id")
        target_user = get_object_or_404(User, id=target_user_id)
        
        # Security: Ensure this user is actually in this chama
        if not Membership.objects.filter(membership_user=target_user, membership_chama=chama).exists():
            messages.error(request, "User does not belong to this chama.")
            return redirect("chama:manage_members", pk=chama_id)

        # Update fields
        target_user.user_first_name = request.POST.get("first_name")
        target_user.user_last_name = request.POST.get("last_name")
        target_user.user_phone_number = request.POST.get("phone_number")
        target_user.save()
        
        messages.success(request, f"Profile updated for {target_user.user_first_name}.")
    
    return redirect("chama:manage_members", pk=chama_id)


@login_required
def assign_role(request, chama_id, user_id):
    """Assign a role (Treasurer/Secretary) to a member (Admin only)."""
    chama = get_object_or_404(Chama, id=chama_id)
    
    if not is_chama_admin(request.user, chama):
        messages.error(request, "Only Admins can assign roles.")
        return redirect("chama:manage_members", pk=chama_id)

    if request.method == 'POST':
        role = request.POST.get('role')
        member = Membership.objects.filter(membership_chama=chama, membership_user_id=user_id).first()
        if member:
            member.membership_role = role
            member.save()
            messages.success(request, f"Role updated to {role.title()}.")
            
            Notification.objects.create(
                notification_user=member.membership_user,
                notification_chama=chama,
                notification_title="Role Promoted",
                notification_message=f"You have been promoted to {role.title()}.",
                notification_type="announcement",
                notification_sender=request.user
            )

    return redirect("chama:manage_members", pk=chama_id)


@login_required
def demote_member(request, chama_id, user_id):
    """Demote a member to regular member role (Admin only)."""
    chama = get_object_or_404(Chama, id=chama_id)
    if not is_chama_admin(request.user, chama):
        messages.error(request, "Only Admins can demote members.")
        return redirect("chama:manage_members", pk=chama_id)

    member = Membership.objects.filter(membership_chama=chama, membership_user_id=user_id).first()
    
    # Allow demoting ANYONE except yourself
    if member.membership_user == request.user:
        messages.error(request, "You cannot demote yourself.")
        return redirect("chama:manage_members", pk=chama_id)

    member.membership_role = 'member'
    member.save()

    Notification.objects.create(
        notification_user=member.membership_user,
        notification_chama=chama,
        notification_title="Role Update",
        notification_message=f"You have been demoted to a regular Member.",
        notification_type="announcement",
        notification_sender=request.user
    )

    messages.success(request, f"{member.membership_user.get_full_name()} has been demoted.")
    return redirect("chama:manage_members", pk=chama_id)


@login_required
def remove_member(request, chama_id, user_id):
    """Permanently delete a member from the chama."""
    chama = get_object_or_404(Chama, id=chama_id)
    if not is_admin_or_secretary(request.user, chama):
        messages.error(request, "Unauthorized.")
        return redirect("chama:manage_members", pk=chama_id)

    member = Membership.objects.filter(membership_chama=chama, membership_user_id=user_id).first()
    
    # Allow deleting ANYONE except yourself
    if member.membership_user == request.user:
        messages.error(request, "You cannot remove yourself from the group here.")
        return redirect("chama:manage_members", pk=chama_id)

    member.delete()
    messages.success(request, "Member removed from the Chama.")
    return redirect("chama:manage_members", pk=chama.id)