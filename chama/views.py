from django.shortcuts import render
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from chama.models import Chama, Membership, JoinRequest
from chama.forms import ChamaForm, ChamaPaymentForm
from chama.utils import is_chama_admin, is_chama_secretary, is_admin_or_secretary

app_name = 'chama'

# View 1: List All Chamas

@login_required(login_url="login")
def chama_list(request):
    """Show all available chamas."""
    chamas = Chama.objects.all().order_by('-chama_created_at')

     # Get IDs of chamas where the user has pending join requests
    user_join_requests = JoinRequest.objects.filter(
        join_request_user=request.user,
        join_request_status='pending'
    ).values_list('join_request_chama_id', flat=True)

    context = {
        'chamas': chamas,
        'user_join_requests': user_join_requests,
    }
    return render(request, 'chama/chama_list.html', {'chamas': chamas})

# View 2: Create a New Chama
@login_required(login_url="login")
def create_chama(request):
    payment_form = ChamaPaymentForm() 
    """Allow any logged-in user to create a chama."""
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
# View 3: Chama Detail

@login_required(login_url='login')
def chama_detail(request, pk):
    """Show chama details, members, and join requests (for admins/secretaries)."""
    chama = get_object_or_404(Chama, pk=pk)
    members = Membership.objects.filter(membership_chama=chama)
    current_members = members.count()
    max_members = chama.chama_max_members
    remaining_slots = max_members - current_members

    # Role checks
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

# View 4: Edit Chama (Admin/Secretary Only)

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

# View 5: Request to Join a Chama

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

# view 6: Shows only the chamas the current logged in user belong to
@login_required(login_url='login')
def my_chamas(request):
    """Display the chamas the logged-in user belongs to."""
    memberships = Membership.objects.select_related('membership_chama').filter(
        membership_user=request.user,
        membership_status='active'
    )
    chamas = [m.membership_chama for m in memberships]

    for chama in chamas:
        # All members regardless of status
        chama.all_members = Membership.objects.filter(
            membership_chama=chama
        ).select_related('membership_user')

        chama.member_count = chama.all_members.count()
        chama.max_members = chama.chama_max_members  # assuming this field exists

    context = {
        "chamas": chamas,
        "memberships": memberships
    }
    return render(request, "chama/my_chamas.html", context)
# View 7: Handle Join Requests (Admin/Secretary Only)

@login_required(login_url='login')
def handle_join_request(request, request_id, action):
    join_request = get_object_or_404(JoinRequest, id=request_id)
    chama = join_request.join_request_chama

    if not is_admin_or_secretary(request.user, chama):
        messages.error(request, "You don't have permission to manage join requests.")
        return redirect('chama:chama_detail', pk=chama.pk)

    if action == 'accept':
        Membership.objects.create(
            membership_user=join_request.join_request_user,
            membership_chama=chama,
            membership_role='member'
        )
        join_request.join_request_status = 'accepted'
        messages.success(request, f"{join_request.join_request_user} added to {chama.chama_name}.")
    elif action == 'reject':
        join_request.join_request_status = 'rejected'
        messages.warning(request, f"Join request from {join_request.join_request_user} rejected.")

    join_request.join_request_reviewed_by = request.user
    join_request.join_request_reviewed_at = timezone.now()
    join_request.save()
    return redirect('chama:chama_detail', pk=chama.pk)

# View 8: Suspend a Member (Admin/Secretary Only)

@login_required(login_url='login')

def suspend_member(request, membership_id):
    membership = get_object_or_404(Membership, id=membership_id)
    chama = membership.membership_chama

    if not is_admin_or_secretary(request.user, chama):
        messages.error(request, "You don't have permission to suspend members.")
        return redirect('chama:chama_detail', pk=chama.pk)

    membership.membership_status = 'inactive'
    membership.save()
    messages.warning(request, f"{membership.membership_user} has been suspended.")
    return redirect('chama:chama_detail', pk=chama.pk)

