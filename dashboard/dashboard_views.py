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
            return render(request, "dashboard/member_dashboard.html", {"error": "No Chama Selected"})

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

    # F. Notifications
    unread_notifications = Notification.objects.filter(
        notification_user=request.user,
        notification_chama=active_chama,
        notification_is_read=False
    ).order_by('-notification_created_at')[:5]

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
        "notifications": unread_notifications,
        
        # Chart Data (JSON for JS)
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
    }
    return render(request, "dashboard/member_dashboard.html", context)
# ==========================================
#              ADMIN DASHBOARD
# ==========================================

@login_required
def admin_dashboard(request, chama_id=None):
    memberships = Membership.objects.filter(
        membership_user=request.user,
        membership_status="active"
    ).select_related("membership_chama")

    user_chamas = [m.membership_chama.id for m in memberships]

    # If user has only one chama and no ID is provided, redirect to it
    if len(user_chamas) == 1 and chama_id is None:
        only_chama_id = user_chamas[0]
        return redirect("dashboard:admin_dashboard", chama_id=only_chama_id)

    active_chama = None
    active_role = None

    if chama_id:
        chama_id = int(chama_id)
        if chama_id not in user_chamas:
            return render(request, "dashboard/admin_dashboard.html", {
                "error": "You do not belong to this chama.",
            })
        active_chama = Chama.objects.get(id=chama_id)
        membership = Membership.objects.filter(
            membership_chama=active_chama,
            membership_user=request.user
        ).first()
        active_role = membership.membership_role if membership else None

    # --- Calculate Metrics ---
    if active_chama:
        # 1. Total Members
        total_members = Membership.objects.filter(
            membership_chama=active_chama,
            membership_status="active"
        ).count()

        # 2. Total Funds (Success contributions)
        total_contributions = Contribution.objects.filter(
            contribution_chama=active_chama,
            contribution_status="success"
        ).aggregate(total=Sum("contribution_amount"))["total"] or 0

        # 3. Pending Actions
        pending_contributions = Contribution.objects.filter(
            contribution_chama=active_chama,
            contribution_status="pending"
        ).count()

        pending_payments = LoanRepayment.objects.filter(
            loan_repayment_loan__loan_chama=active_chama
        ).count() # This counts pending loan repayment approvals

        # 4. Chama Balance (Total In - Total Outstanding Loans)
        total_loan_outstanding = Loan.objects.filter(
            loan_chama=active_chama
        ).aggregate(out=Sum("loan_outstanding_balance"))["out"] or 0

        chama_balance = total_contributions - total_loan_outstanding

        # --- Treasurer Metrics (for reused components) ---
        contributions_qs = Contribution.objects.filter(
            contribution_chama=active_chama,
            contribution_status="success"
        )
        collected = total_contributions
        target = active_chama.chama_target_amount
        progress_percent = (collected / target * 100) if target > 0 else 0

    else:
        # Default zero values if no chama selected
        total_members = total_contributions = pending_contributions = 0
        pending_payments = total_loan_outstanding = chama_balance = 0
        collected = target = progress_percent = 0

    context = {
        "active_chama": active_chama,
        "active_role": active_role,
        "chama_with_roles": memberships,
        # Metrics for Cards
        "total_members": total_members,
        "total_contributions": total_contributions,
        "pending_contributions": pending_contributions,
        "pending_payments": pending_payments,
        "chama_balance": chama_balance,
        # Extra Treasurer Metrics if needed
        "collected": collected,
        "target": target,
        "progress_percent": progress_percent,
    }
    return render(request, "dashboard/admin_dashboard.html", context)


@login_required
@require_POST
def assign_role(request, chama_id):
    """
    Handles role assignment from the Admin Dashboard Modal.
    """
    chama = get_object_or_404(Chama, id=chama_id)
    
    # 1. Verify Requesting User is Admin
    requester_membership = Membership.objects.filter(
        membership_user=request.user, 
        membership_chama=chama, 
        membership_role='admin'
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
    if not Membership.objects.filter(membership_user=request.user, membership_chama=chama, membership_role='admin').exists():
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
    if not Membership.objects.filter(membership_user=request.user, membership_chama=chama, membership_role='admin').exists():
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
    
    if report_type == 'full' and membership.membership_role != 'admin':
        return HttpResponseForbidden("Unauthorized: Only Admins can download full reports.")
    
    if report_type == 'finance' and membership.membership_role not in ['admin', 'treasurer']:
        return HttpResponseForbidden("Unauthorized: Only Treasurers/Admins can download finance reports.")

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
    return render(request, "dashboard/treasurer_dashboard.html", context)


# ==========================================
#           SECRETARY DASHBOARD
# ==========================================

@login_required
def secretary_dashboard(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
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

    # Average attendance (last meeting)
    last_meeting = Meeting.objects.filter(meeting_chama=chama, meeting_status="completed").order_by("-meeting_date").first()
    avg_attendance = last_meeting.attendance_rate if last_meeting else 0

    # Unread notifications
    unread_notifications = Notification.objects.filter(notification_user=request.user, notification_is_read=False).count()

    context = {
        "chama": chama,
        "total_members": total_members,
        "active_members": active_members,
        "inactive_members": inactive_members,
        "new_members_this_month": new_members_this_month,
        "upcoming_meetings": upcoming_meetings,
        "avg_attendance": avg_attendance,
        "unread_notifications": unread_notifications,
    }
    return render(request, "dashboard/secretary_dashboard.html", context)


@login_required
def secretary_join_requests(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
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
            join_req.save()
            Notification.objects.create(
                notification_user=join_req.join_request_user,
                notification_chama=chama,
                notification_title="Join Request Approved",
                notification_message=f"Your request to join {chama.chama_name} was approved.",
                notification_type="member_joined",
                notification_sender=request.user
            )
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

    join_requests = JoinRequest.objects.filter(join_request_chama=chama, join_request_status="pending")
    return render(request, "chama/join_requests.html", {"join_requests": join_requests})


@login_required
def mark_attendance(request, chama_id, meeting_id):
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

    attendees = Membership.objects.filter(membership_chama=chama, membership_status="active")
    return render(request, "notification/meeting/admin_meeting_list.html", {"meeting": meeting, "attendees": attendees})


@login_required
def upload_meeting_file(request, chama_id, meeting_id):
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

    return redirect("dashboard:meeting_detail", chama_id=chama.id, meeting_id=meeting.id)


@login_required
def send_reminder(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)

    if membership.membership_role != "secretary":
        return HttpResponseForbidden("Not allowed.")

    if request.method == "POST":
        message = request.POST.get("message")
        for member in Membership.objects.filter(membership_chama=chama, membership_status="active"):
            Notification.objects.create(
                notification_user=member.membership_user,
                notification_chama=chama,
                notification_title="Reminder",
                notification_message=message,
                notification_type="reminder",
                notification_sender=request.user
            )

    return redirect("dashboard:secretary_dashboard", chama_id=chama.id)