from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from chama.models import Chama, Membership, JoinRequest
from chama.forms import ChamaForm, ChamaPaymentForm
from chama.utils import is_chama_admin, is_chama_secretary, is_admin_or_secretary

app_name = 'chama'
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Chama, Membership, JoinRequest

# --- VIEW 1: The Page for Officials ---
@login_required
def manage_members(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    
    # Security: Ensure only Admin, Secretary, or Treasurer can view this
    user_role = Membership.objects.filter(membership_user=request.user, membership_chama=chama).first()
    if not user_role or user_role.membership_role not in ['admin', 'secretary', 'treasurer']:
        messages.error(request, "You are not authorized to manage members.")
        return redirect('chama:chama_details', chama_id=chama.id)

    members = Membership.objects.filter(membership_chama=chama).order_by('-membership_join_date')
    
    context = {
        'chama': chama,
        'members': members,
        'user_role': user_role.membership_role, # pass current user's role to template
    }
    return render(request, 'chama/manage_members.html', context)

# --- ACTION 2: Assign Role (AJAX Logic) ---
@login_required
def assign_role(request):
    if request.method == "POST":
        data = json.loads(request.body)
        membership_id = data.get('membership_id')
        new_role = data.get('new_role')
        
        # Get the membership being changed
        target_membership = get_object_or_404(Membership, id=membership_id)
        chama = target_membership.membership_chama
        
        # Security: Only an Admin of that specific Chama can assign roles
        current_user_membership = Membership.objects.get(
            membership_user=request.user, 
            membership_chama=chama
        )
        
        if current_user_membership.membership_role != 'admin':
            return JsonResponse({'success': False, 'message': 'Only Admins can assign roles.'})
            
        # Update the role
        target_membership.membership_role = new_role
        target_membership.save()
        
        # NOTIFICATION LOGIC here
        # For now, we return a success message, but here is where you would trigger an email/SMS
        # Example: notify_user(target_membership.membership_user, f"Your role is now {new_role}")

        return JsonResponse({'success': True, 'message': f'Role updated to {new_role} successfully.'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})

# --- ACTION 3: Handle Join Request (Accept/Decline) ---
@login_required
def handle_join_request(request, request_id, action):
    join_req = get_object_or_404(JoinRequest, id=request_id)
    chama = join_req.join_request_chama
    
    # Security check (Admin/Secretary only)
    if not Membership.objects.filter(membership_user=request.user, membership_chama=chama, membership_role__in=['admin', 'secretary']).exists():
        return JsonResponse({'success': False, 'message': 'Unauthorized'})

    if action == 'accept':
        join_req.join_request_status = 'accepted'
        join_req.save()
        
        # Create Membership
        Membership.objects.create(
            membership_user=join_req.join_request_user,
            membership_chama=chama,
            membership_role='member'
        )
        
        # Notification Logic
        messages.success(request, f"{join_req.join_request_user.first_name} has been added.")
        # Notify user: "Your request to join... has been accepted"
        
    elif action == 'decline':
        join_req.join_request_status = 'rejected'
        join_req.save()
        messages.info(request, "Request declined.")

    return JsonResponse({'success': True})

# List All Chamas
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

# Create a New Chama
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

# Chama Detail
@login_required(login_url='login')
def chama_detail(request, pk):
    chama = get_object_or_404(Chama, pk=pk)
    members = Membership.objects.filter(membership_chama=chama)
    current_members = members.count()
    max_members = chama.chama_max_members
    remaining_slots = max_members - current_members
    is_admin = is_chama_admin(request.user, chama)
    is_secretary = is_chama_secretary(request.user, chama)
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
        'current_members': current_members,
        'max_members': max_members,
        'remaining_slots': remaining_slots,
    }
    return render(request, 'chama/chama_detail.html', context)

# Edit Chama (Admin/Secretary Only)
@login_required(login_url='login')
def edit_chama(request, pk):
    chama = get_object_or_404(Chama, pk=pk)
    if not is_admin_or_secretary(request.user, chama):
        messages.error(request, "You don't have permission to edit this chama.")
        return redirect('chama:chama_detail', pk=chama.pk)

    if request.method == 'POST':
        form = ChamaForm(request.POST, instance=chama)
        if form.is_valid():
            form.save()
            messages.success(request, "Chama details updated successfully.")
            return redirect('chama:chama_detail', pk=chama.pk)
    else:
        form = ChamaForm(instance=chama)
    return render(request, 'chama/create_chama.html', {'form': form, 'edit_mode': True})

# My Chamas
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

# Join a Chama
@login_required(login_url='login')
def join_chama(request, pk):
    chama = get_object_or_404(Chama, pk=pk)
    current_members = Membership.objects.filter(membership_chama=chama).count()

    if current_members >= chama.chama_max_members:
        messages.warning(request, f"'{chama.chama_name}' is already full.")
        return redirect('chama:chama_detail', pk=chama.pk)

    if Membership.objects.filter(membership_user=request.user, membership_chama=chama).exists():
        messages.info(request, "You are already a member of this chama.")
        return redirect('chama:chama_detail', pk=chama.pk)

    existing_request = JoinRequest.objects.filter(
        join_request_user=request.user,
        join_request_chama=chama,
        join_request_status='pending'
    ).first()

    if existing_request:
        messages.warning(request, "You already have a pending join request.")
    else:
        JoinRequest.objects.create(join_request_user=request.user, join_request_chama=chama)
        messages.success(request, f"Join request sent to '{chama.chama_name}'.")

    return redirect('chama:chama_detail', pk=chama.pk)

# Accept Request
@login_required
def accept_request(request, request_id):
    join_request = get_object_or_404(JoinRequest, id=request_id)
    chama = join_request.join_request_chama
    membership = Membership.objects.filter(membership_user=request.user, membership_chama=chama).first()
    if not membership or membership.membership_role not in ["admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")

    join_request.join_request_status = "accepted"
    join_request.save()
    Membership.objects.create(
        membership_user=join_request.join_request_user,
        membership_chama=chama,
        membership_role="member"
    )

    messages.success(request, f"{join_request.join_request_user.user_first_name} has been added to the chama.")
    return redirect("chama:join_requests", pk=chama.id)

# Reject Request
@login_required
def reject_request(request, request_id):
    join_request = get_object_or_404(JoinRequest, id=request_id)
    chama = join_request.join_request_chama
    membership = Membership.objects.filter(membership_user=request.user, membership_chama=chama).first()
    if not membership or membership.membership_role not in ["admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")

    join_request.join_request_status = "rejected"
    join_request.save()

    messages.error(request, f"Join request from {join_request.join_request_user.user_first_name} has been rejected.")
    return redirect("chama:join_requests", pk=chama.id)

# Remove a User
@login_required
def remove_member(request, chama_id, user_id):
    chama = get_object_or_404(Chama, id=chama_id)
    membership = Membership.objects.filter(membership_user=request.user, membership_chama=chama).first()
    if not membership or membership.membership_role not in ["admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")

    member = Membership.objects.filter(membership_chama=chama, membership_user_id=user_id).first()
    if not member:
        messages.error(request, "User is not a member.")
        return redirect("chama:chama_detail", pk=chama.id)

    member.delete()
    messages.success(request, "Member removed successfully.")
    return redirect("chama:chama_detail", pk=chama.id)

# Join Requests
@login_required(login_url='login')
def join_requests(request, pk):
    """Show all pending join requests for a chama (admin/secretary only)."""
    chama = get_object_or_404(Chama, pk=pk)
    if not is_admin_or_secretary(request.user, chama):
        return HttpResponseForbidden("Unauthorized")

    requests = JoinRequest.objects.filter(
        join_request_chama=chama,
        join_request_status='pending'
    ).select_related('join_request_user')

    context = {
        'chama': chama,
        'join_requests': requests,
    }
    return render(request, 'chama/join_requests.html', context)

@login_required(login_url='login')
def members(request, pk):
    chama = get_object_or_404(Chama, pk=pk)
    membership = Membership.objects.filter(membership_user=request.user, membership_chama=chama).first()

    # Only admins/secretaries can view/manage members
    if not membership or membership.membership_role not in ["admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")

    members = Membership.objects.filter(membership_chama=chama).select_related("membership_user")

    context = {
        "chama": chama,
        "members": members,
    }
    return render(request, "chama/members.html", context)
