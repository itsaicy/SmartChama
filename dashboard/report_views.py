import csv
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from chama.models import Chama, Membership
from finance.models import Contribution, Loan, Penalty, ContributionCycle, LoanRepayment
from notification.models import Notification, Meeting, MeetingAttendance

# Helper to safely get user name
def get_member_name(user):
    if hasattr(user, 'get_full_name') and user.get_full_name():
        return user.get_full_name()
    return user.user_first_name or "Unknown"

# ---------------------- Financial Report (Treasurer & Admin) ----------------------
@login_required
def download_financial_report(request, chama_id):
    user = request.user
    chama = Chama.objects.get(id=chama_id)

    membership = Membership.objects.filter(
        membership_user=user,
        membership_chama=chama,
        membership_status='active',
        membership_role__in=['treasurer', 'admin']
    ).first()
    
    if not membership:
        return HttpResponse("You do not have permission to download this report.", status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{chama.chama_name}_financial_report.csv"'

    writer = csv.writer(response)
    writer.writerow(["Category", "User/Item", "Amount", "Date", "Status", "Details"])

    # 1. Contributions
    for c in Contribution.objects.filter(contribution_chama=chama):
        writer.writerow([
            "Contribution",
            get_member_name(c.contribution_user),
            c.contribution_amount,
            c.contribution_created_at.strftime("%Y-%m-%d"),
            c.contribution_status,
            c.contribution_type
        ])

    # 2. Loans Issued
    for l in Loan.objects.filter(loan_chama=chama):
        writer.writerow([
            "Loan Issued",
            get_member_name(l.loan_user),
            l.loan_amount,
            l.loan_created_at.strftime("%Y-%m-%d"),
            l.loan_status,
            f"Outstanding: {l.loan_outstanding_balance}"
        ])

    # 3. Loan Repayments
    for lr in LoanRepayment.objects.filter(loan_repayment_loan__loan_chama=chama):
        # FIX: Changed loan_repayment_date to loan_repayment_time
        writer.writerow([
            "Loan Repayment",
            get_member_name(lr.loan_repayment_loan.loan_user),
            lr.loan_repayment_amount,
            lr.loan_repayment_time.strftime("%Y-%m-%d"), 
            "Paid",
            f"Repayment for Loan ID {lr.loan_repayment_loan.id}"
        ])

    # 4. Penalties
    for p in Penalty.objects.filter(penalty_chama=chama):
        writer.writerow([
            "Penalty",
            get_member_name(p.penalty_user),
            p.penalty_amount,
            p.penalty_created_at.strftime("%Y-%m-%d"),
            "Paid" if p.penalty_paid else "Unpaid",
            p.penalty_reason
        ])

    return response


# ---------------------- Full Report (Admin Only) ----------------------
@login_required
def download_full_report(request, chama_id):
    user = request.user
    chama = Chama.objects.get(id=chama_id)

    # Permission check
    membership = Membership.objects.filter(
        membership_user=user,
        membership_chama=chama,
        membership_status='active',
        membership_role='admin'
    ).first()
    
    if not membership:
        return HttpResponse("You do not have permission to download this report.", status=403)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{chama.chama_name}_full_data_export.csv"'

    writer = csv.writer(response)
    writer.writerow(["Section", "Item Type", "Related User", "Value/Amount", "Date", "Status", "Description/Details"])

    # --- 1. MEMBERSHIP DATA ---
    for m in Membership.objects.filter(membership_chama=chama):
        join_date = m.membership_join_date.strftime("%Y-%m-%d") if m.membership_join_date else "N/A"
        writer.writerow([
            "Membership", 
            "Member Profile", 
            get_member_name(m.membership_user),
            "", 
            join_date,
            m.membership_status, 
            f"Role: {m.membership_role} | Phone: {m.membership_user.user_phone_number}"
        ])

    # --- 2. CONTRIBUTION CYCLES ---
    for cycle in ContributionCycle.objects.filter(cycle_chama=chama):
        writer.writerow([
            "Operations",
            "Contribution Cycle",
            "Everyone",
            cycle.cycle_amount_required,
            f"{cycle.cycle_created_at.strftime('%Y-%m-%d')} to {cycle.cycle_deadline}",
            cycle.cycle_status,
            f"Name: {cycle.cycle_name}"
        ])

    # --- 3. CONTRIBUTIONS ---
    for c in Contribution.objects.filter(contribution_chama=chama):
        writer.writerow([
            "Financial", 
            "Contribution", 
            get_member_name(c.contribution_user),
            c.contribution_amount, 
            c.contribution_created_at.strftime("%Y-%m-%d"),
            c.contribution_status, 
            f"Type: {c.contribution_type}"
        ])

    # --- 4. LOANS & REPAYMENTS ---
    for l in Loan.objects.filter(loan_chama=chama):

        writer.writerow([
            "Financial", 
            "Loan Issued", 
            get_member_name(l.loan_user),
            l.loan_amount, 
            l.loan_created_at.strftime("%Y-%m-%d"),
            l.loan_status, 
            f"Due: {l.loan_deadline} | Outstanding: {l.loan_outstanding_balance}"
        ])
        for lr in LoanRepayment.objects.filter(loan_repayment_loan=l):
            
            writer.writerow([
                "Financial",
                "Loan Repayment",
                get_member_name(l.loan_user),
                lr.loan_repayment_amount,
                lr.loan_repayment_time.strftime("%Y-%m-%d"),
                "Success",
                f"Ref: {lr.loan_repayment_reference or 'N/A'}"
            ])

    # --- 5. PENALTIES ---
    for p in Penalty.objects.filter(penalty_chama=chama):
        writer.writerow([
            "Financial", 
            "Penalty", 
            get_member_name(p.penalty_user),
            p.penalty_amount, 
            p.penalty_created_at.strftime("%Y-%m-%d"),
            "Paid" if p.penalty_paid else "Unpaid", 
            p.penalty_reason
        ])

    # --- 6. MEETINGS & ATTENDANCE ---
    for meeting in Meeting.objects.filter(meeting_chama=chama):
        writer.writerow([
            "Operations",
            "Meeting Event",
            "All Members",
            "",
            meeting.meeting_date.strftime("%Y-%m-%d"),
            meeting.meeting_status,
            f"Title: {meeting.meeting_title} | Location: {meeting.meeting_venue}"
        ])
        for att in MeetingAttendance.objects.filter(attendance_meeting=meeting):
            writer.writerow([
                "Operations",
                "Meeting Attendance",
                get_member_name(att.attendance_user),
                "",
                meeting.meeting_date.strftime("%Y-%m-%d"),
                att.attendance_status,
                f"Notes: {att.attendance_notes or 'None'}"
            ])

    # --- 7. NOTIFICATIONS ---
    for note in Notification.objects.filter(notification_chama=chama):
        writer.writerow([
            "Communication",
            "Notification",
            get_member_name(note.notification_user),
            "", 
            note.notification_created_at.strftime("%Y-%m-%d"),
            "Read" if note.notification_is_read else "Unread",
            f"Title: {note.notification_title} | Msg: {note.notification_message}"
        ])

    return response