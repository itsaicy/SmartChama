import csv
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.db.models import Sum, Count, Q
import json
from django.db.models.functions import TruncMonth
from user.models import User
from chama.models import Membership, Chama, JoinRequest
from notification.models import NotificationReply, Notification, Meeting, MeetingAttendance
from finance.models import Contribution, LoanRepayment, Loan, ContributionCycle, Penalty
from darajaapi.models import Transaction
from chama.utils import get_user_dashboard_redirect

# --- NEW HELPER FUNCTION for Notifications ---
def get_notification_context(user, active_chama):
    """Fetches unread count and latest 5 unread notifications for the active chama."""
    if not active_chama:
        return {"unread_count": 0, "latest_notifications": []}

    qs = Notification.objects.filter(
        notification_user=user,
        notification_chama=active_chama,
        notification_is_read=False
    ).order_by('-notification_created_at')
    
    return {
        "unread_count": qs.count(),
        "latest_notifications": qs[:5],
    }
# ---------------------------------------------


@login_required
def dashboard(request):
    """
    Redirects the user to their appropriate dashboard based on their active role or default logic.
    """
    return redirect(get_user_dashboard_redirect(request.user))


@login_required
def dashboard_search(request, chama_id):
    """
    Global search within the dashboard context.
    """
    chama = get_object_or_404(Chama, id=chama_id)
    query = request.GET.get('q')
    memberships = Membership.objects.filter(membership_chama=chama, membership_status='active')
    
    if query:
        memberships = memberships.filter(
            Q(membership_user__user_first_name__icontains=query) |
            Q(membership_user__user_last_name__icontains=query) |
            Q(membership_user__user_email__icontains=query) |
            Q(membership_user__user_phone_number__icontains=query)
        )
    
    context = {
        "chama": chama,
        "results": memberships,
        "query": query
    }
    # Add notifications to context
    active_chama = Chama.objects.filter(id=chama_id).first()
    context.update(get_notification_context(request.user, active_chama))
    return render(request, "dashboard/search_results.html", context)


@login_required
def switch_role(request, chama_id, role):
    """
    Context switcher: Updates session variables to change the user's current 'Active Chama' and 'Role'.
    """
    membership = Membership.objects.filter(
        membership_user=request.user,
        membership_chama_id=chama_id,
        membership_role=role,
        membership_status='active'
    ).first()

    if not membership:
        messages.error(request, "You don't have that role in this chama.")
        return redirect('dashboard:dashboard')

    # Save active session context
    request.session['active_chama_id'] = chama_id
    request.session['active_chama_name'] = membership.membership_chama.chama_name
    request.session['active_role'] = role

    messages.success(
        request,
        f"Switched to {role.title()} role in {membership.membership_chama.chama_name}"
    )

    # Redirect based on role
    if role == "admin":
        return redirect("dashboard:admin_dashboard", chama_id=chama_id)
    elif role == "treasurer":
        return redirect("dashboard:treasurer_dashboard", chama_id=chama_id)
    elif role == "secretary":
        return redirect("dashboard:secretary_dashboard", chama_id=chama_id)
    else:
        return redirect("dashboard:member_dashboard", chama_id=chama_id)


# ==========================================
#              MEMBER DASHBOARD
# ==========================================

@login_required
def member_dashboard(request, chama_id=None):
    # 1. Session Context
    active_role = request.session.get('active_role', 'member')
    
    # 2. Determine Active Chama
    if chama_id:
        active_chama = get_object_or_404(Chama, id=chama_id)
        # Update session to keep context
        request.session['active_chama_id'] = active_chama.id
        request.session['active_chama_name'] = active_chama.chama_name
    else:
        # Fallback to session or first chama
        chama_id = request.session.get('active_chama_id')
        if chama_id:
            active_chama = get_object_or_404(Chama, id=chama_id)
        else:
            # Handle case where user has no chama context yet
            active_chama = None
            context = {"error": "No Chama Selected"}
            context.update(get_notification_context(request.user, active_chama))
            return render(request, "dashboard/member_dashboard.html", context)

    # 3. --- CARDS DATA ---

    # A. Contribution Status (Current Cycle)
    current_cycle = ContributionCycle.objects.filter(cycle_chama=active_chama, cycle_status='open').first()
    contrib_status = "No Active Cycle"
    contrib_color = "secondary"
    
    if current_cycle:
        has_paid = Contribution.objects.filter(
            contribution_user=request.user,
            contribution_cycle=current_cycle,
            contribution_chama=active_chama
        ).exists()
        
        if has_paid:
            contrib_status = "Paid"
            contrib_color = "success"
        elif timezone.now().date() > current_cycle.cycle_deadline:
            contrib_status = "Overdue"
            contrib_color = "danger"
        else:
            contrib_status = "Pending"
            contrib_color = "warning"

    # B. My Loans (Active Loan & Progress)
    active_loan = Loan.objects.filter(
        loan_user=request.user, 
        loan_chama=active_chama, 
        loan_status='active'
    ).first()
    
    loan_progress = 0
    if active_loan and active_loan.loan_amount > 0:
        # Calculate percentage paid
        amount_paid = active_loan.loan_amount - active_loan.loan_outstanding_balance
        loan_progress = (amount_paid / active_loan.loan_amount) * 100

    # C. My Penalties (Aggregated)
    penalties_data = Penalty.objects.filter(
        penalty_user=request.user,
        penalty_chama=active_chama,
        penalty_paid=False
    ).aggregate(
        count=Count('id'), 
        total=Sum('penalty_amount')
    )
    total_penalty_amount = penalties_data['total'] or 0
    total_penalty_count = penalties_data['count'] or 0

    # D. Chama Goal Progress (Read Only for Member)
    chama_target = active_chama.chama_target_amount
    total_collected = Contribution.objects.filter(
        contribution_chama=active_chama, 
        contribution_status='success'
    ).aggregate(sum=Sum('contribution_amount'))['sum'] or 0
    
    chama_progress = 0
    if chama_target > 0:
        chama_progress = (total_collected / chama_target) * 100

    # 4. --- WIDGETS DATA ---

    # E. Next Meeting Countdown
    next_meeting = Meeting.objects.filter(
        meeting_chama=active_chama,
        meeting_date__gte=timezone.now()
    ).order_by('meeting_date').first()

    attendance_status = "N/A"
    if next_meeting:
        att = MeetingAttendance.objects.filter(attendance_meeting=next_meeting, attendance_user=request.user).first()
        if att:
            attendance_status = att.attendance_status

    # F. Notifications - REMOVED: Now handled by helper function
    
    # 5. --- GRAPHS DATA (My Monthly Contributions) ---
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_stats = Contribution.objects.filter(
        contribution_user=request.user,
        contribution_chama=active_chama,
        contribution_created_at__gte=six_months_ago,
        contribution_status='success'
    ).annotate(
        month=TruncMonth('contribution_created_at')
    ).values('month').annotate(
        total=Sum('contribution_amount')
    ).order_by('month')

    # Prepare data for Chart.js
    chart_labels = []
    chart_data = []
    for entry in monthly_stats:
        chart_labels.append(entry['month'].strftime('%b %Y'))
        chart_data.append(float(entry['total']))

    context = {
        "active_chama": active_chama,
        "active_role": active_role,
        
        # Cards Data
        "contrib_status": contrib_status,
        "contrib_color": contrib_color,
        "active_loan": active_loan,
        "loan_progress": loan_progress,
        "total_penalty_amount": total_penalty_amount,
        "total_penalty_count": total_penalty_count,
        "chama_target": chama_target,
        "chama_progress": chama_progress,
        
        # Widgets
        "next_meeting": next_meeting,
        "attendance_status": attendance_status,
        
        # Chart Data (JSON for JS)
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
    }
    context.update(get_notification_context(request.user, active_chama))
    return render(request, "dashboard/member_dashboard.html", context)
# ==========================================
#              ADMIN DASHBOARD
# ==========================================


# --- HELPER FUNCTION for Notifications ---
def get_notification_context(user, active_chama):
    """Fetches unread count and latest 5 unread notifications for the active chama."""
    if not active_chama:
        return {"unread_count": 0, "latest_notifications": []}

    qs = Notification.objects.filter(
        notification_user=user,
        notification_chama=active_chama,
        notification_is_read=False
    ).order_by('-notification_created_at')
    
    return {
        "unread_count": qs.count(),
        "latest_notifications": qs[:5],
    }

# --- HELPER FUNCTION for Recent Activity ---
def get_recent_activity(chama, limit=4):
    """
    Fetches the 4 most recent activities across the chama.
    Returns a list of activity dictionaries with type, description, and timestamp.
    """
    activities = []
    
    # Recent Contributions
    recent_contributions = Contribution.objects.filter(
        contribution_chama=chama,
        contribution_status='success'
    ).order_by('-contribution_created_at')[:limit]
    
    for contrib in recent_contributions:
        activities.append({
            'type': 'contribution',
            'icon': 'fa-coins',
            'color': 'success',
            'description': f"{contrib.contribution_user.get_full_name()} contributed Ksh {contrib.contribution_amount}",
            'timestamp': contrib.contribution_created_at
        })
    
    # Recent Loans
    recent_loans = Loan.objects.filter(
        loan_chama=chama
    ).order_by('-loan_created_at')[:limit]
    
    for loan in recent_loans:
        activities.append({
            'type': 'loan',
            'icon': 'fa-hand-holding-usd',
            'color': 'warning',
            'description': f"{loan.loan_user.get_full_name()} took a loan of Ksh {loan.loan_amount}",
            'timestamp': loan.loan_created_at
        })
    
    # Recent Penalties
    recent_penalties = Penalty.objects.filter(
        penalty_chama=chama
    ).order_by('-penalty_created_at')[:limit]
    
    for penalty in recent_penalties:
        activities.append({
            'type': 'penalty',
            'icon': 'fa-exclamation-triangle',
            'color': 'danger',
            'description': f"{penalty.penalty_user.get_full_name()} received a penalty of Ksh {penalty.penalty_amount}",
            'timestamp': penalty.penalty_created_at
        })
    
    # Recent Join Requests
    recent_joins = JoinRequest.objects.filter(
        join_request_chama=chama,
        join_request_status='accepted'
    ).order_by('-join_request_reviewed_at')[:limit]
    
    for join in recent_joins:
        activities.append({
            'type': 'join',
            'icon': 'fa-user-plus',
            'color': 'info',
            'description': f"{join.join_request_user.get_full_name()} joined the chama",
            'timestamp': join.join_request_reviewed_at or join.join_request_created_at
        })
    
    # Sort all activities by timestamp (most recent first) and return top 4
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    return activities[:limit]


@login_required
def admin_dashboard(request, chama_id=None):
    # Get all user's memberships with their roles
    memberships = Membership.objects.filter(
        membership_user=request.user,
        membership_status="active"
    ).select_related("membership_chama")

    user_chamas = [m.membership_chama.id for m in memberships]

    active_chama = None
    active_role = None

    if chama_id:
        chama_id = int(chama_id)
        if chama_id not in user_chamas:
            pass 
        else:
            active_chama = Chama.objects.get(id=chama_id)
            membership = Membership.objects.filter(
                membership_chama=active_chama,
                membership_user=request.user
            ).first()
            active_role = membership.membership_role if membership else None
    
    # If user has only one chama and no ID is provided, set it as active
    if active_chama is None and len(user_chamas) == 1:
        active_chama = Chama.objects.get(id=user_chamas[0])
        membership = Membership.objects.filter(
            membership_chama=active_chama,
            membership_user=request.user
        ).first()
        active_role = membership.membership_role if membership else None
    
    # Redirect if context is missing/invalid after checks
    if active_chama is None:
        context = {"error": "You do not belong to this chama or no chama is selected."}
        context.update(get_notification_context(request.user, None))
        return render(request, "dashboard/admin_dashboard.html", context)
        
    # --- Calculate Metrics ---

    # 1. Total Members
    total_members = Membership.objects.filter(
        membership_chama=active_chama,
        membership_status="active"
    ).count()

    # 2. Total Contributions (Success only)
    contributions_qs = Contribution.objects.filter(
        contribution_chama=active_chama,
        contribution_status="success"
    )
    total_contributions = contributions_qs.aggregate(total=Sum("contribution_amount"))["total"] or 0

    # 3. Pending Contributions (by type)
    pending_contributions_regular = Contribution.objects.filter(
        contribution_chama=active_chama,
        contribution_status="pending",
        contribution_type='contribution'
    )
    pending_regular_count = pending_contributions_regular.count()
    pending_regular_amount = pending_contributions_regular.aggregate(total=Sum("contribution_amount"))["total"] or 0

    # 4. Pending Loan Requests
    pending_loan_requests = Loan.objects.filter(
        loan_chama=active_chama,
        loan_status="pending"
    )
    pending_loans_count = pending_loan_requests.count()

    # 5. Today's STK Summary
    today = timezone.now().date()
    today_tx = Transaction.objects.filter(
        transaction_chama=active_chama,
        transaction_created_at__date=today
    )
    stk_success = today_tx.filter(transaction_status="success").count()
    stk_failed = today_tx.filter(transaction_status="failed").count()
    stk_pending = today_tx.filter(transaction_status="pending").count()

    # 6. Penalties Overview
    all_penalties_qs = Penalty.objects.filter(penalty_chama=active_chama)
    unpaid_penalties = all_penalties_qs.filter(penalty_paid=False)
    total_penalty_amount = all_penalties_qs.aggregate(total=Sum("penalty_amount"))["total"] or 0
    unpaid_penalty_amount = unpaid_penalties.aggregate(total=Sum("penalty_amount"))["total"] or 0
    unpaid_penalty_count = unpaid_penalties.count()

    # 7. Contribution History (Last 6 Months)
    six_months_ago = timezone.now() - timedelta(days=180)
    contributions_history = (
        contributions_qs.filter(contribution_time__gte=six_months_ago)
        .annotate(month=TruncMonth('contribution_time'))
        .values("month")
        .annotate(total=Sum("contribution_amount"))
        .order_by("month")
    )
    contributions_history_list = list(contributions_history)

    # 8. Progress Toward Chama Target
    target = active_chama.chama_target_amount
    collected = total_contributions
    progress_percent = (collected / target * 100) if target > 0 else 0

    # 9. Pending Join Requests (For validation)
    pending_join_requests = JoinRequest.objects.filter(
        join_request_chama=active_chama,
        join_request_status="pending"
    )
    pending_join_count = pending_join_requests.count()

    # 10. Recent Activity (NEW)
    recent_activities = get_recent_activity(active_chama, limit=4)

    context = {
        "active_chama": active_chama,
        "active_role": active_role,
        "chama_with_roles": memberships,
        
        # --- CARDS DATA (Only what's needed) ---
        "total_members": total_members,
        "total_contributions": total_contributions,
        
        # Pending Contributions Card
        "pending_regular_count": pending_regular_count,
        "pending_regular_amount": pending_regular_amount,
        
        # Pending Loan Requests Card
        "pending_loans_count": pending_loans_count,
        "pending_loan_requests": pending_loan_requests,
        
        # Today's STK Summary Card
        "stk_success": stk_success,
        "stk_failed": stk_failed,
        "stk_pending": stk_pending,
        
        # Penalties Overview Card
        "total_penalty_amount": total_penalty_amount,
        "unpaid_penalty_amount": unpaid_penalty_amount,
        "unpaid_penalty_count": unpaid_penalty_count,
        
        # Contribution History (Last 6 Months) - For Chart
        "contributions_history": contributions_history_list,
        
        # Progress Toward Chama Target Card
        "target": target,
        "collected": collected,
        "progress_percent": progress_percent,
        
        # Join Requests (for validation/debugging)
        "pending_join_count": pending_join_count,
        
        # Recent Activity (NEW)
        "recent_activities": recent_activities,
    }
    
    context.update(get_notification_context(request.user, active_chama))
    return render(request, "dashboard/admin_dashboard.html", context)


@login_required
@require_POST
def assign_role(request, chama_id):
    """
    Handles role assignment from the Admin Dashboard Modal.
    """
    chama = get_object_or_404(Chama, id=chama_id)
    # ... (rest of assign_role remains the same)
    
    # 1. Verify Requesting User is Admin
    requester_membership = Membership.objects.filter(
        membership_user=request.user, 
        membership_chama=chama, 
        membership_role__in=['admin', 'chairman']
    ).first()
    
    if not requester_membership:
        messages.error(request, "Unauthorized action.")
        return redirect("dashboard:admin_dashboard", chama_id=chama_id)

    # 2. Get Form Data
    target_user_id = request.POST.get("user_id")
    new_role = request.POST.get("new_role")
    
    # 3. Get Target Membership
    target_membership = get_object_or_404(Membership, membership_user_id=target_user_id, membership_chama=chama)
    
    # 4. Update Role
    target_membership.membership_role = new_role
    target_membership.save()
    
    # 5. Send Notification
    Notification.objects.create(
        notification_user=target_membership.membership_user,
        notification_chama=chama,
        notification_title="Role Updated",
        notification_message=f"Hey {target_membership.membership_user.user_first_name}, you are now a {new_role.title()} of {chama.chama_name}.",
        notification_type="announcement", 
        notification_sender=request.user
    )
    
    messages.success(request, f"Role updated for {target_membership.membership_user.get_full_name()} to {new_role.title()}.")
    return redirect("dashboard:admin_dashboard", chama_id=chama_id)


# --- ADMIN MEMBER CRUD OPERATIONS ---

@login_required
def edit_member(request, chama_id):
    """
    Updates member details (First Name, Last Name, Phone) from the Admin Modal.
    """
    chama = get_object_or_404(Chama, id=chama_id)
    
    # Verify Admin
    if not Membership.objects.filter(membership_user=request.user, membership_chama=chama, membership_role__in=['admin', 'chairman']).exists():
        messages.error(request, "Unauthorized.")
        return redirect("dashboard:admin_dashboard", chama_id=chama_id)

    if request.method == "POST":
        target_user_id = request.POST.get("user_id")
        target_user = get_object_or_404(User, id=target_user_id)
        
        # Update fields
        target_user.user_first_name = request.POST.get("first_name")
        target_user.user_last_name = request.POST.get("last_name")
        target_user.user_phone_number = request.POST.get("phone")
        target_user.save()
        
        messages.success(request, f"Profile updated for {target_user.user_first_name}.")
    
    return redirect("dashboard:admin_dashboard", chama_id=chama_id)


@login_required
def delete_member(request, chama_id, user_id):
    """
    Permanently removes a member from the database.
    """
    chama = get_object_or_404(Chama, id=chama_id)
    
    # Verify Admin
    if not Membership.objects.filter(membership_user=request.user, membership_chama=chama, membership_role__in=['admin', 'chairman']).exists():
        messages.error(request, "Unauthorized.")
        return redirect("dashboard:admin_dashboard", chama_id=chama_id)

    target_user = get_object_or_404(User, id=user_id)
    
    # Prevent Admin from deleting themselves
    if target_user == request.user:
        messages.error(request, "You cannot delete your own account while logged in.")
        return redirect("dashboard:admin_dashboard", chama_id=chama_id)

    # Delete User
    target_user.delete()
    messages.success(request, "User deleted from database.")
    return redirect("dashboard:admin_dashboard", chama_id=chama_id)


# ==========================================
#           PROFILE & REPORTING
# ==========================================

# ... (update_profile_picture and download_report remain the same as they don't impact the dashboard header)

@login_required
def update_profile_picture(request):
    """
    Handles profile picture upload.
    """
    if request.method == 'POST' and request.FILES.get('profile_image'):
        user = request.user
        user.user_profile_picture = request.FILES['profile_image']
        user.save()
        messages.success(request, "Profile picture updated successfully!")
    else:
        messages.error(request, "Failed to upload image. Please ensure you selected a file.")
    
    # Redirect back to the page they came from
    return redirect(request.META.get('HTTP_REFERER', 'dashboard:dashboard'))


@login_required
def download_report(request, chama_id, report_type):
    """
    Generates CSV reports for Admins (Full Report) and Treasurers (Finance Report).
    """
    chama = get_object_or_404(Chama, id=chama_id)
    
    # Security Check: Ensure user belongs to the Chama and has permission
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)
    
    if report_type == 'full' and membership.membership_role not in ['admin', 'chairman']:
        return HttpResponseForbidden("Unauthorized: Only Admins/Chairmen can download full reports.")
    
    if report_type == 'finance' and membership.membership_role not in ['admin', 'chairman', 'treasurer']:
        return HttpResponseForbidden("Unauthorized: Only Treasurers/Admins/Chairmen can download finance reports.")

    # Create Response
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{chama.chama_name}_{report_type}_report.csv"'},
    )

    writer = csv.writer(response)
    
    if report_type == 'full':
        # Admin Full Report
        writer.writerow(['Member Name', 'Email', 'Phone', 'Role', 'Join Date', 'Total Contributed', 'Loan Status'])
        members = Membership.objects.filter(membership_chama=chama)
        
        for m in members:
            total_contributed = Contribution.objects.filter(
                contribution_user=m.membership_user, 
                contribution_chama=chama
            ).aggregate(Sum('contribution_amount'))['contribution_amount__sum'] or 0
            
            # Check for active loan
            has_loan = Loan.objects.filter(loan_user=m.membership_user, loan_chama=chama, loan_status='active').exists()
            loan_status = "Has Active Loan" if has_loan else "No Active Loan"

            writer.writerow([
                m.membership_user.get_full_name(),
                m.membership_user.user_email,
                m.membership_user.user_phone_number,
                m.membership_role.title(),
                m.membership_join_date.strftime("%Y-%m-%d"),
                total_contributed,
                loan_status
            ])
            
    elif report_type == 'finance':
        # Treasurer Finance Report
        writer.writerow(['Transaction ID', 'User', 'Type', 'Amount', 'Date', 'Status'])
        txs = Transaction.objects.filter(transaction_chama=chama).order_by('-transaction_created_at')
        
        for tx in txs:
            writer.writerow([
                tx.transaction_id, 
                tx.transaction_user.get_full_name(), 
                tx.transaction_type, 
                tx.transaction_amount, 
                tx.transaction_created_at.strftime("%Y-%m-%d %H:%M"), 
                tx.transaction_status
            ])

    return response


# ==========================================
#           TREASURER DASHBOARD
# ==========================================

@login_required
def treasurer_dashboard(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    active_chama = chama # Alias for consistency

    # --- 1. Total Funds ---
    month = request.GET.get("month")  # dropdown filter
    contributions_qs = Contribution.objects.filter(contribution_chama=chama, contribution_status="success")
    if month:
        contributions_qs = contributions_qs.filter(contribution_time__month=month)
    total_funds = contributions_qs.aggregate(total=Sum("contribution_amount"))["total"] or 0
    
    member_contributions = contributions_qs.values("contribution_user__user_first_name").annotate(
        total=Sum("contribution_amount")
    )

    # --- 2. Goal Progress ---
    collected = total_funds
    target = chama.chama_target_amount
    progress_percent = (collected / target * 100) if target > 0 else 0

    # --- 3. Pending / Overdue Contributions ---
    cycle = ContributionCycle.objects.filter(cycle_chama=chama, cycle_status="open").last()
    pending_members = Membership.objects.filter(membership_chama=chama, membership_status="active").exclude(
        membership_user__in=contributions_qs.values("contribution_user")
    )
    pending_count = pending_members.count()
    pending_amount = pending_count * (cycle.cycle_amount_required if cycle else chama.chama_contribution_amount)

    # --- 4. Pending Loans ---
    pending_loans = Loan.objects.filter(loan_chama=chama, loan_status="pending")

    # --- 5. Active Loans ---
    active_loans = Loan.objects.filter(loan_chama=chama, loan_status="active")
    active_loans_count = active_loans.count()
    total_loaned = active_loans.aggregate(total=Sum("loan_amount"))["total"] or 0
    total_outstanding = active_loans.aggregate(total=Sum("loan_outstanding_balance"))["total"] or 0
    repayment_progress = (total_loaned - total_outstanding) / total_loaned * 100 if total_loaned > 0 else 0

    # --- 6. Penalties ---
    penalties = Penalty.objects.filter(penalty_chama=chama)
    missed_payments = penalties.filter(penalty_reason__icontains="missed").count()
    loan_defaults = penalties.filter(penalty_reason__icontains="default").count()
    total_penalties = penalties.aggregate(total=Sum("penalty_amount"))["total"] or 0

    # --- 7. STK Monitor (Today’s Transactions) ---
    today = timezone.now().date()
    today_tx = Transaction.objects.filter(transaction_chama=chama, transaction_created_at__date=today)
    stk_success = today_tx.filter(transaction_status="success").count()
    stk_failed = today_tx.filter(transaction_status="failed").count()

    # --- 8. Charts ---
    six_months_ago = timezone.now() - timedelta(days=180)
    contributions_history = (
        contributions_qs.filter(contribution_time__gte=six_months_ago)
        .values("contribution_time__month")
        .annotate(total=Sum("contribution_amount"))
    )

    # Pie chart: cycle status
    # Note: Using contribution count (paid) and penalty count (overdue) as proxies here.
    paid = contributions_qs.count() 
    pending = pending_count
    overdue = penalties.count()

    context = {
        "chama": chama,
        "total_funds": total_funds,
        "member_contributions": member_contributions,
        "collected": collected,
        "target": target,
        "progress_percent": progress_percent,
        "pending_count": pending_count,
        "pending_amount": pending_amount,
        "pending_loans": pending_loans,
        "active_loans_count": active_loans_count,
        "total_loaned": total_loaned,
        "total_outstanding": total_outstanding,
        "repayment_progress": repayment_progress,
        "missed_payments": missed_payments,
        "loan_defaults": loan_defaults,
        "total_penalties": total_penalties,
        "stk_success": stk_success,
        "stk_failed": stk_failed,
        "contributions_history": list(contributions_history),
        "cycle_status": {"paid": paid, "pending": pending, "overdue": overdue},
    }
    context.update(get_notification_context(request.user, active_chama))
    return render(request, "dashboard/treasurer_dashboard.html", context)


# ==========================================
#           SECRETARY DASHBOARD
# ==========================================

# In dashboard/dashboard_views.py

@login_required
def secretary_dashboard(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    active_chama = chama # Alias for consistency
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=chama,
        membership_status="active"
    )

    if membership.membership_role != "secretary":
        return HttpResponseForbidden("Not allowed.")

    # Total members
    total_members = Membership.objects.filter(membership_chama=chama).count()
    active_members = Membership.objects.filter(membership_chama=chama, membership_status="active").count()
    inactive_members = total_members - active_members

    # FIXED CALCULATION: Active Member Percentage
    active_percentage = 0
    if total_members > 0:
        active_percentage = (active_members / total_members) * 100

    # New members this month
    now = timezone.now()
    new_members_this_month = Membership.objects.filter(
        membership_chama=chama,
        membership_join_date__month=now.month,
        membership_join_date__year=now.year
    ).count()

    # Upcoming meetings (this week only)
    start_week = now - timedelta(days=now.weekday())
    end_week = start_week + timedelta(days=7)
    upcoming_meetings = Meeting.objects.filter(
        meeting_chama=chama,
        meeting_date__range=(start_week, end_week),
        meeting_status="scheduled"
    )
    
    # Join Requests (Added here to ensure template rendering works)
    join_requests = JoinRequest.objects.filter(join_request_chama=chama, join_request_status="pending")

    # Average attendance (last meeting)
    last_meeting = Meeting.objects.filter(meeting_chama=chama, meeting_status="completed").order_by("-meeting_date").first()
    # Assuming attendance_rate is a property or method on the Meeting model that calculates the average rate
    avg_attendance = last_meeting.attendance_rate if last_meeting and hasattr(last_meeting, 'attendance_rate') else 0 


    context = {
        "chama": chama,
        "total_members": total_members,
        "active_members": active_members,
        "inactive_members": inactive_members,
        "new_members_this_month": new_members_this_month,
        "upcoming_meetings": upcoming_meetings,
        "avg_attendance": avg_attendance,
        "active_percentage": active_percentage, # <-- NEW CONTEXT VARIABLE
        "join_requests": join_requests, # Ensure join_requests is passed for the card
        "now": now, # Pass 'now' for the new members month display
    }
    context.update(get_notification_context(request.user, active_chama))
    return render(request, "dashboard/secretary_dashboard.html", context)

@login_required
def secretary_join_requests(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    # ... (rest of secretary_join_requests remains the same)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)

    if membership.membership_role != "secretary":
        return HttpResponseForbidden("Not allowed.")

    if request.method == "POST":
        action = request.POST.get("action")
        join_id = request.POST.get("join_id")
        join_req = get_object_or_404(JoinRequest, id=join_id, join_request_chama=chama)

        if action == "approve":
            join_req.join_request_status = "accepted"
            join_req.join_request_reviewed_by = request.user
            join_req.join_request_reviewed_at = timezone.now()
            
            # Create Membership after approval (assuming this logic is correct)
            Membership.objects.create(
                membership_chama=chama,
                membership_user=join_req.join_request_user,
                membership_role='member',
                membership_status='active',
            )
            join_req.save()
            
            Notification.objects.create(
                notification_user=join_req.join_request_user,
                notification_chama=chama,
                notification_title="Join Request Approved",
                notification_message=f"Your request to join {chama.chama_name} was approved.",
                notification_type="member_joined",
                notification_sender=request.user
            )
            messages.success(request, f"Approved {join_req.join_request_user.get_full_name()} to join.")
        elif action == "reject":
            join_req.join_request_status = "rejected"
            join_req.join_request_reviewed_by = request.user
            join_req.join_request_reviewed_at = timezone.now()
            join_req.save()
            Notification.objects.create(
                notification_user=join_req.join_request_user,
                notification_chama=chama,
                notification_title="Join Request Rejected",
                notification_message=f"Your request to join {chama.chama_name} was rejected.",
                notification_type="member_joined",
                notification_sender=request.user
            )
            messages.warning(request, f"Rejected {join_req.join_request_user.get_full_name()}'s request.")
        
        return redirect("dashboard:secretary_join_requests", chama_id=chama.id)


    join_requests = JoinRequest.objects.filter(join_request_chama=chama, join_request_status="pending")
    
    active_chama = chama
    context = {"join_requests": join_requests, "active_chama": active_chama}
    context.update(get_notification_context(request.user, active_chama))
    return render(request, "chama/join_requests.html", context)


@login_required
def mark_attendance(request, chama_id, meeting_id):
    # ... (mark_attendance remains the same)
    chama = get_object_or_404(Chama, id=chama_id)
    meeting = get_object_or_404(Meeting, id=meeting_id, meeting_chama=chama)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)

    if membership.membership_role != "secretary":
        return HttpResponseForbidden("Not allowed.")

    if request.method == "POST":
        member_id = request.POST.get("member_id")
        status = request.POST.get("status")  # present/absent/excused
        att, created = MeetingAttendance.objects.update_or_create(
            attendance_meeting=meeting,
            attendance_user_id=member_id,
            defaults={"attendance_status": status}
        )
        if status == "absent":
            Notification.objects.create(
                notification_user=att.attendance_user,
                notification_chama=chama,
                notification_title="Attendance Marked Absent",
                notification_message=f"You were marked absent for {meeting.meeting_title}. Confirm or decline.",
                notification_type="meeting",
                notification_sender=request.user,
                notification_related_meeting=meeting
            )
        messages.success(request, f"Attendance marked as {status.title()} for member ID {member_id}.")
        return redirect(request.META.get('HTTP_REFERER', 'dashboard:secretary_dashboard'))


    attendees = Membership.objects.filter(membership_chama=chama, membership_status="active")
    active_chama = chama
    context = {"meeting": meeting, "attendees": attendees, "active_chama": active_chama}
    context.update(get_notification_context(request.user, active_chama))
    return render(request, "notification/meeting/admin_meeting_list.html", context)


@login_required
def upload_meeting_file(request, chama_id, meeting_id):
    # ... (upload_meeting_file remains the same)
    chama = get_object_or_404(Chama, id=chama_id)
    meeting = get_object_or_404(Meeting, id=meeting_id, meeting_chama=chama)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)

    if membership.membership_role != "secretary":
        return HttpResponseForbidden("Not allowed.")

    if request.method == "POST" and request.FILES.get("file"):
        NotificationReply.objects.create(
            notification_reply_notification=meeting.meeting_notification,
            notification_reply_user=request.user,
            notification_reply_message="Meeting document uploaded",
            notification_reply_attachment=request.FILES["file"]
        )
        Notification.objects.create(
            notification_user=request.user,
            notification_chama=chama,
            notification_title="Meeting Document Uploaded",
            notification_message=f"A new document was uploaded for {meeting.meeting_title}.",
            notification_type="meeting",
            notification_sender=request.user,
            notification_related_meeting=meeting
        )
        messages.success(request, "Meeting file uploaded successfully.")

    # Note: Assuming 'dashboard:meeting_detail' is a valid URL, otherwise check URL structure
    return redirect("dashboard:meeting_detail", chama_id=chama.id, meeting_id=meeting.id)


@login_required
def send_reminder(request, chama_id):
    # ... (send_reminder remains the same)
    chama = get_object_or_404(Chama, id=chama_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)

    if membership.membership_role != "secretary":
        return HttpResponseForbidden("Not allowed.")

    if request.method == "POST":
        message = request.POST.get("message")
        count = 0
        for member in Membership.objects.filter(membership_chama=chama, membership_status="active"):
            Notification.objects.create(
                notification_user=member.membership_user,
                notification_chama=chama,
                notification_title="Reminder",
                notification_message=message,
                notification_type="reminder",
                notification_sender=request.user
            )
            count += 1
        messages.success(request, f"Reminder sent to {count} active members.")

    return redirect("dashboard:secretary_dashboard", chama_id=chama.id)