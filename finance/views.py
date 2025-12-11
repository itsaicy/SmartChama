import base64
import datetime
import json
import requests
import uuid
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib.auth import get_user_model

# --- Local Imports ---
from darajaapi.accesstoken import access_token
from darajaapi.stk_push import initiate_stk_push
from darajaapi.models import Transaction 
from chama.models import Chama, Membership
from .models import (
    Contribution, ContributionCycle, Penalty, Loan,
    LoanRepayment, CONTRIBUTION_TYPE_CHOICES, CYCLE_TYPE_CHOICES
)
from common.utils import paginate_queryset, send_chama_notification

User = get_user_model() # Get the actual User model class

# ==========================================
#  1. CONTRIBUTION CYCLES
# ==========================================

@login_required
def list_cycles(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)
    active_members_count = Membership.objects.filter(
        membership_chama=chama, 
        membership_status='active'
    ).count()

    # 2. Fetch Cycles
    cycles_qs = ContributionCycle.objects.filter(cycle_chama=chama).order_by('-cycle_deadline')
    
    cycles_data = []
    
    for cycle in cycles_qs:
        total_target = cycle.cycle_amount_required or 0
        if active_members_count > 0:
            per_member_share = total_target / active_members_count
        else:
            per_member_share = 0
            
        paid_amount = Contribution.objects.filter(
            contribution_chama=chama,
            contribution_user=request.user,
            contribution_cycle=cycle,
            contribution_status='success'
        ).aggregate(Sum('contribution_amount'))['contribution_amount__sum'] or 0

        balance = per_member_share - paid_amount
        if balance < 0: balance = 0

        # C. Attach data to cycle object
        cycle.per_member_share = per_member_share
        cycle.user_paid = paid_amount
        cycle.user_balance = balance
        cycle.is_fully_paid = (balance < 1) # Treat less than 1 KES as paid to avoid rounding issues
        
        cycles_data.append(cycle)

    return render(request, "finance/list_cycles.html", {
        "chama": chama,
        "cycles": cycles_data,
        "membership": membership,
    })

@login_required
def create_cycle(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)

    if membership.membership_role not in ["treasurer", "admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")

    if request.method == "POST":
        try:
            cycle_name = request.POST.get("cycle_name")
            cycle_type = request.POST.get("cycle_type")
            cycle_amount = Decimal(request.POST.get("cycle_amount"))
            cycle_deadline = request.POST.get("cycle_deadline")
            beneficiary_id = request.POST.get("beneficiary_id") or None

            cycle = ContributionCycle.objects.create(
                cycle_chama=chama,
                cycle_name=cycle_name,
                cycle_type=cycle_type,
                cycle_amount_required=cycle_amount,
                cycle_deadline=cycle_deadline,
                cycle_beneficiary_id=beneficiary_id,
                cycle_status='open'
            )
            
            # Notify members
            members = Membership.objects.filter(membership_chama=chama, membership_status='active').select_related('membership_user')
            recipients = [m.membership_user for m in members]
            send_chama_notification(
                chama=chama, recipients=recipients, title=f"New Cycle: {cycle_name}",
                message=f"New cycle '{cycle_name}' created. Amount: KES {cycle_amount}. Deadline: {cycle_deadline}.",
                sender=request.user, n_type="announcement"
            )

            messages.success(request, "Cycle created successfully.")
            return redirect("finance:cycle_detail", cycle_id=cycle.id)
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return redirect("finance:list_cycles", chama_id=chama.id)

    # Redirect GET requests back to the list (since it's a modal)
    return redirect("finance:list_cycles", chama_id=chama.id)

@login_required
def cycle_detail(request, cycle_id):
    cycle = get_object_or_404(ContributionCycle, id=cycle_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=cycle.cycle_chama)
    
    contributions = Contribution.objects.filter(contribution_cycle=cycle).select_related("contribution_user").order_by("-contribution_created_at")
    
    # Identify non-contributors for UI display
    contributed_ids = contributions.filter(contribution_status="success").values_list("contribution_user", flat=True)
    non_contributors = Membership.objects.filter(
        membership_chama=cycle.cycle_chama,
        membership_status="active"
    ).exclude(membership_user_id__in=contributed_ids)
    
    # Fetch all members for Edit Cycle Modal dropdown
    all_members = Membership.objects.filter(membership_chama=cycle.cycle_chama).select_related('membership_user')


    return render(request, "finance/cycle_detail.html", {
        "cycle": cycle,
        "membership": membership,
        "contributions": contributions,
        "non_contributors": non_contributors,
        "members": all_members # Pass members for edit modal dropdown
    })

@login_required
def close_cycle(request, cycle_id):
    cycle = get_object_or_404(ContributionCycle, id=cycle_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=cycle.cycle_chama)

    if membership.membership_role not in ["treasurer", "admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")

    if request.method == "POST":
        cycle.cycle_status = "closed"
        cycle.save()

        members = Membership.objects.filter(membership_chama=cycle.cycle_chama, membership_status="active")
        recipients = [m.membership_user for m in members]
        send_chama_notification(
            chama=cycle.cycle_chama, recipients=recipients, title=f"Cycle Closed: {cycle.cycle_name}",
            message=f"The cycle '{cycle.cycle_name}' has been closed.", sender=request.user, n_type="announcement"
        )

        messages.success(request, f"Cycle '{cycle.cycle_name}' closed.")
        return redirect("finance:cycle_detail", cycle_id=cycle.id)

    return render(request, "finance/close_cycle.html", {"cycle": cycle})

# In finance/views.py

@login_required
def check_contribution_status(request, contribution_id):
    """
    Checks the status of a specific transaction actively against Daraja
    and updates the local database immediately.
    """
    try:
        # 1. Get the contribution
        contrib = Contribution.objects.get(id=contribution_id, contribution_user=request.user)
        
        # 2. Only query Daraja if it's still marked as 'pending' locally
        if contrib.contribution_status == 'pending' and contrib.contribution_reference:
            
            # --- PREPARE DARAJA QUERY ---
            Timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            query_url = "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query"
            BusinessShortCode = settings.MPESA_SHORTCODE
            passkey = settings.MPESA_PASSKEY
            Password = base64.b64encode(f"{BusinessShortCode}{passkey}{Timestamp}".encode()).decode()
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token()}"
            }
            payload = {
                "BusinessShortCode": BusinessShortCode,
                "Password": Password,
                "Timestamp": Timestamp,
                "CheckoutRequestID": contrib.contribution_reference
            }
            
            try:
                # 3. SEND QUERY
                response = requests.post(query_url, json=payload, headers=headers)
                data = response.json()
                
                # 4. PARSE RESULT
                result_code = str(data.get('ResultCode'))
                
                if result_code == '0':
                    # SUCCESS
                    contrib.contribution_status = 'success'
                    # Extract Receipt if available
                    if 'CallbackMetadata' in data:
                        items = data['CallbackMetadata'].get('Item', [])
                        for item in items:
                            if item.get('Name') == 'MpesaReceiptNumber':
                                contrib.contribution_mpesa_receipt = item.get('Value')
                    contrib.save()
                    
                elif result_code == '1032':
                    # CANCELLED
                    contrib.contribution_status = 'cancelled'
                    contrib.save()
                    
                elif result_code and result_code not in ['0', '1032', '1037']:
                    # FAILED (1037 is "Timeout" meaning still pending, so we ignore it)
                    contrib.contribution_status = 'failed'
                    contrib.save()
                    
            except Exception as e:
                # If internet fails, just ignore and return current local status
                print(f"Error querying Daraja: {str(e)}")

        # 5. Return the (possibly updated) status
        return JsonResponse({'status': contrib.contribution_status})
        
    except Contribution.DoesNotExist:
        return JsonResponse({'status': 'unknown'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@login_required
def send_contribution_reminder(request, cycle_id):
    cycle = get_object_or_404(ContributionCycle, id=cycle_id)
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=cycle.cycle_chama
    )

    if membership.membership_role not in ["treasurer", "admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")

    contributed_ids = Contribution.objects.filter(
        contribution_cycle=cycle,
        contribution_status="success"
    ).values_list("contribution_user_id", flat=True)

    non_contrib_members = Membership.objects.filter(
        membership_chama=cycle.cycle_chama,
        membership_status="active"
    ).exclude(membership_user_id__in=contributed_ids).select_related("membership_user")

    recipients = [m.membership_user for m in non_contrib_members]
    
    if not recipients:
        messages.info(request, "Everyone has contributed! No reminders sent.")
        return redirect("finance:cycle_detail", cycle_id=cycle.id)

    send_chama_notification(
        chama=cycle.cycle_chama,
        recipients=recipients,
        title=f"Reminder: {cycle.cycle_name}",
        message=f"Reminder to pay KES {cycle.cycle_amount_required} for '{cycle.cycle_name}' by {cycle.cycle_deadline}.",
        sender=request.user,
        n_type="reminder",
        priority="high"
    )

    messages.success(request, f"Reminders sent to {len(recipients)} members.")
    return redirect("finance:cycle_detail", cycle_id=cycle.id)

@login_required
def edit_cycle(request, cycle_id):
    cycle = get_object_or_404(ContributionCycle, id=cycle_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=cycle.cycle_chama)
    if membership.membership_role not in ["treasurer", "admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")

    if request.method == "POST":
        cycle.cycle_name = request.POST.get("cycle_name")
        cycle.cycle_amount_required = Decimal(request.POST.get("cycle_amount"))
        cycle.cycle_deadline = request.POST.get("cycle_deadline")
        
        # Add beneficiary update logic if needed
        beneficiary_id = request.POST.get("beneficiary_id")
        if beneficiary_id:
             cycle.cycle_beneficiary_id = beneficiary_id

        cycle.save()
        messages.success(request, "Cycle updated.")
    return redirect("finance:cycle_detail", cycle_id=cycle.id)

@login_required
def delete_cycle(request, cycle_id):
    cycle = get_object_or_404(ContributionCycle, id=cycle_id)
    chama_id = cycle.chama.id
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=cycle.chama)
    if membership.membership_role not in ["treasurer", "admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")
    
    cycle.delete()
    messages.success(request, "Cycle deleted.")
    return redirect("finance:list_cycles", chama_id=chama_id)


# ==========================================
#  2. CONTRIBUTIONS & TRANSACTIONS
# ==========================================

@login_required
def list_contributions(request, chama_id):
    """
    Displays ONLY the logged-in user's personal contributions/transactions.
    This applies to everyone: Members, Admins, and Treasurers.
    """
    chama = get_object_or_404(Chama, id=chama_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)

    contributions = Contribution.objects.filter(
        contribution_chama=chama, 
        contribution_user=request.user
    )

    status_filter = request.GET.get("status")
    if status_filter:
        contributions = contributions.filter(contribution_type=status_filter)

    contributions = contributions.order_by("-contribution_created_at")
    contributions_page = paginate_queryset(contributions, request.GET.get("page"))

    return render(request, "finance/list_contributions.html", {
        "chama": chama,
        "membership": membership,
        "contributions": contributions_page,
    })

@login_required
def chama_all_contributions(request, chama_id):
    """
    Displays ALL contributions for the Chama.
    Accessible ONLY by Admin, Treasurer, or Chairman.
    """
    chama = get_object_or_404(Chama, id=chama_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)

    # ✅ SECURITY: Strict check for officials
    if membership.membership_role not in ["treasurer", "admin", "chairman"]:
        messages.error(request, "Access Denied: You are not authorized to view the master ledger.")
        return redirect('finance:list_contributions', chama_id=chama.id)

    # ✅ LOGIC: Fetch ALL transactions (No user filter)
    contributions = Contribution.objects.filter(contribution_chama=chama)

    # Optional: Filter by specific member (search functionality)
    member_search_id = request.GET.get("member_id")
    if member_search_id:
        contributions = contributions.filter(contribution_user_id=member_search_id)

    # Apply Status Filter
    status_filter = request.GET.get("status")
    if status_filter:
        contributions = contributions.filter(contribution_type=status_filter)

    contributions = contributions.order_by("-contribution_created_at")
    contributions_page = paginate_queryset(contributions, request.GET.get("page"))

    return render(request, "finance/all_contributions.html", {
        "chama": chama,
        "membership": membership,
        "contributions": contributions_page,
    })

@login_required
def create_contribution(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    active_cycles = ContributionCycle.objects.filter(
        cycle_chama=chama, cycle_status='open', cycle_deadline__gte=timezone.now().date()
    )

    if request.method == 'POST':
        try:
            cycle_id = request.POST.get('cycle_id')
            cycle = ContributionCycle.objects.get(id=cycle_id) if cycle_id else None
            amount = Decimal(request.POST.get('amount'))
            phone = request.POST.get('phone')
            ctype = request.POST.get('contribution_type', 'contribution')

            # Call initiate_stk_push with correct arguments
            result = initiate_stk_push(
                request.user,
                chama,
                phone, 
                amount,
                ctype, 
            )

            if not result.get("success"):
                # FIX: Convert error message to string to avoid Decimal serialization issues
                error_message = str(result.get("errorMessage", "Payment initiation failed."))
                messages.error(request, error_message)
                return redirect("finance:create_contribution", chama_id=chama_id)

            # Record Pending Contribution
            Contribution.objects.create(
                contribution_user=request.user,
                contribution_chama=chama,
                contribution_cycle=cycle,
                contribution_amount=amount,
                contribution_type=ctype,
                contribution_phone=phone,
                contribution_status="pending",
                contribution_reference=result.get("CheckoutRequestID"),
                contribution_time=timezone.now()
            )
            
            messages.success(request, "STK push initiated. Check your phone.")
            return redirect("finance:list_contributions", chama_id=chama_id)
            
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, "finance/create_contribution.html", {
        "chama": chama,
        "active_cycles": active_cycles,
        "user": request.user
    })

@login_required
def member_dues(request, user_id):
    """
    Individual Member Dues View:
    - Allows a regular member to see THEIR own debt.
    - Allows Admins/Treasurers to see ANYONE'S debt.
    """
    try:
        # Get the context of the logged-in user
        user_membership = request.user.memberships.first()
        if not user_membership:
            messages.error(request, "No active membership found.")
            return redirect("dashboard:dashboard")
        
        chama = user_membership.membership_chama
        
        # Security Check: Regular members can only view their OWN dues
        if user_membership.membership_role not in ['treasurer', 'admin', 'chairperson']:
            if request.user.id != user_id:
                messages.error(request, "Unauthorized")
                return redirect('finance:list_contributions', chama_id=chama.id)

        # Fetch the specific member we are looking at
        target_member = get_object_or_404(User, id=user_id)

        # 1. Active Loans for this user
        loans = Loan.objects.filter(
            loan_chama=chama, 
            loan_user=target_member, 
            loan_status='active'
        )

        # 2. Unpaid Penalties for this user
        penalties = Penalty.objects.filter(
            penalty_chama=chama, 
            penalty_user=target_member, 
            penalty_paid=False
        )

        # 3. Pending Contributions (optional)
        pending_contributions = Contribution.objects.filter(
            contribution_chama=chama,
            contribution_user=target_member,
            contribution_status='pending'
        )
        
        # 4. Calculate Total
        total_penalties = penalties.aggregate(Sum('penalty_amount'))['penalty_amount__sum'] or 0
        total_loans = loans.aggregate(Sum('loan_outstanding_balance'))['loan_outstanding_balance__sum'] or 0
        total_owed = total_penalties + total_loans

        return render(request, "finance/member_dues.html", {
            "chama": chama,
            "member": target_member,
            "total_owed": total_owed,
            "penalties": penalties,
            "loans": loans,
            "pending_contributions": pending_contributions,
        })
    except Exception as e:
        messages.error(request, f"Error retrieving dues: {str(e)}")
        return redirect("dashboard:dashboard")

@login_required
def chama_outstanding_dues(request, chama_id):
    """
    Displays a Master Ledger of ALL outstanding debts (Loans & Penalties) 
    for the entire Chama. Only accessible by officials.
    """
    # 1. Get the Chama
    chama = get_object_or_404(Chama, id=chama_id)
    
    # 2. Get User Membership (Handle Non-Members Gracefully)
    try:
        user_membership = Membership.objects.get(
            membership_user=request.user, 
            membership_chama=chama
        )
    except Membership.DoesNotExist:
        messages.error(request, "You are not a member of this Chama.")
        return redirect('dashboard:dashboard')

    # 3. Check Permissions (Case-Insensitive)
    # We convert to lowercase to ensure 'Admin' matches 'admin'
    current_role = str(user_membership.membership_role).lower()
    allowed_roles = ['treasurer', 'admin', 'chairperson', 'secretary']
    
    if current_role not in allowed_roles:
        messages.error(request, f"Access Denied: {current_role.title()}s cannot view the master dues list.")
        return redirect('finance:list_contributions', chama_id=chama.id)

    # 4. Fetch All Active Loans (Sorted by due date)
    all_loans = Loan.objects.filter(
        loan_chama=chama, 
        loan_status='active'
    ).select_related('loan_user').order_by('loan_deadline')

    # 5. Fetch All Unpaid Penalties (Sorted by newest first)
    all_penalties = Penalty.objects.filter(
        penalty_chama=chama, 
        penalty_paid=False
    ).select_related('penalty_user').order_by('-penalty_created_at')

    # 6. Fetch Pending Transactions (Optional: shows who is currently trying to pay)
    pending_tx = Contribution.objects.filter(
        contribution_chama=chama,
        contribution_status='pending'
    ).select_related('contribution_user').order_by('-contribution_created_at')

    # 7. Calculate Grand Totals (Safely handles None if list is empty)
    total_loans_val = all_loans.aggregate(Sum('loan_outstanding_balance'))['loan_outstanding_balance__sum'] or 0
    total_penalties_val = all_penalties.aggregate(Sum('penalty_amount'))['penalty_amount__sum'] or 0
    total_owed = total_loans_val + total_penalties_val

    # 8. Render the Template
    return render(request, "finance/chama_dues.html", {
        "chama": chama,
        "total_owed": total_owed,
        "loans": all_loans,
        "penalties": all_penalties,
        "pending_contributions": pending_tx,
    })

@login_required
def remind_member_debt(request, user_id):
    # 1. Get the Chama context
    user_membership = request.user.memberships.first()
    if not user_membership:
        messages.error(request, "No active membership found.")
        return redirect("dashboard:dashboard")
        
    target_member = get_object_or_404(User, id=user_id)
    chama = user_membership.membership_chama
    
    send_chama_notification(
        chama=chama,
        recipients=[target_member],
        title="Outstanding Dues Reminder",
        message=f"Hello {target_member.user_first_name}, you have outstanding payments in {chama.chama_name}. Please visit the finance tab to settle them.",
        sender=request.user,
        n_type="reminder",
        priority="high"
    )
    
    messages.success(request, f"Reminder sent to {target_member.get_full_name()}")

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
        
    return redirect('finance:member_dues', user_id=user_id)
# ==========================================
#  3. LOANS
# ==========================================

@login_required
def list_loans(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=chama)

    if membership.membership_role in ["treasurer", "admin"]:
        loans = Loan.objects.filter(loan_chama=chama)
    else:
        loans = Loan.objects.filter(loan_chama=chama, loan_user=request.user)

    loans = loans.order_by("-loan_created_at")
    total_active_value = loans.filter(loan_status='active').aggregate(Sum('loan_amount'))['loan_amount__sum'] or 0

    return render(request, "finance/list_loans.html", {
        "chama": chama,
        "membership": membership,
        "loans": loans,
        "total_active_value": total_active_value,
    })

@login_required
def request_loan(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    
    if request.method == "POST":
        try:
            amount = Decimal(request.POST["amount"])
            rate = Decimal("10.00")
            total = amount + (amount * rate / 100)
            
            loan = Loan.objects.create(
                loan_user=request.user,
                loan_chama=chama,
                loan_amount=amount,
                loan_interest_rate=rate,
                loan_total_payable=total,
                loan_outstanding_balance=total,
                loan_purpose=request.POST.get("purpose"),
                loan_deadline=request.POST.get("deadline"),
                loan_status="pending"
            )

            treasurers = Membership.objects.filter(membership_chama=chama, membership_role='treasurer').select_related('membership_user')
            send_chama_notification(
                chama=chama, recipients=[t.membership_user for t in treasurers],
                title="Loan Request", message=f"{request.user} requested a loan of KES {amount}.",
                sender=request.user, n_type="loan", related_loan=loan
            )

            messages.success(request, "Loan request submitted.")
            return redirect("finance:loan_detail", loan_id=loan.id)
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            
    return redirect("finance:list_loans", chama_id=chama_id)

@login_required
def loan_detail(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=loan.loan_chama)

    repayments = LoanRepayment.objects.filter(loan_repayment_loan=loan).order_by("-loan_repayment_time")
    total_repaid = repayments.aggregate(Sum("loan_repayment_amount"))["loan_repayment_amount__sum"] or 0

    return render(request, "finance/loan_detail.html", {
        "loan": loan,
        "membership": membership,
        "total_repaid": total_repaid,
        "repayments": repayments,
    })

@login_required
def approve_loan(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=loan.loan_chama)

    if membership.membership_role not in ["treasurer", "admin"]:
        return HttpResponseForbidden("Unauthorized")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            loan.loan_status = "approved"
            loan.save()
            send_chama_notification(chama=loan.loan_chama, recipients=[loan.loan_user], title="Loan Approved", message=f"Your loan of KES {loan.loan_amount} is approved.", sender=request.user, n_type="loan", related_loan=loan)
        elif action == "reject":
            loan.loan_status = "rejected"
            loan.save()
            send_chama_notification(chama=loan.loan_chama, recipients=[loan.loan_user], title="Loan Rejected", message="Your loan request was rejected.", sender=request.user, n_type="loan", related_loan=loan)
            
    return redirect("finance:loan_detail", loan_id=loan.id)

@login_required
def disburse_loan(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, loan_status='approved')
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=loan.loan_chama)

    if membership.membership_role not in ["treasurer", "admin"]:
        return HttpResponseForbidden("Unauthorized")

    if request.method == "POST":
        reference = request.POST.get("reference", f"LOAN-{loan.id}")
        loan.loan_status = "active"
        loan.loan_reference = reference
        loan.save()

        send_chama_notification(
            chama=loan.loan_chama,
            recipients=[loan.loan_user],
            title="Loan Disbursed",
            message=f"Your loan of KES {loan.loan_amount} has been disbursed. Ref: {reference}",
            sender=request.user,
            n_type="loan",
            related_loan=loan
        )

        messages.success(request, "Loan marked as disbursed.")
        return redirect("finance:loan_detail", loan_id=loan.id)

    return render(request, "finance/disburse_loan.html", {
        "loan": loan,
        "chama": loan.chama
    })

@login_required
def repay_loan(request, loan_id):
    if loan_id == 0:
        active_loan = Loan.objects.filter(loan_user=request.user, loan_status='active').first()
        if active_loan:
            return redirect("finance:loan_detail", loan_id=active_loan.id)
        else:
             user_membership = request.user.memberships.first()
             if user_membership:
                 chama = user_membership.membership_chama
                 messages.info(request, "Please select a loan to repay from your loans list.")
                 return redirect("finance:list_loans", chama_id=chama.id)
             else:
                 return redirect("dashboard:dashboard")

    loan = get_object_or_404(Loan, id=loan_id)
    
    if request.method == "POST":
        amount = Decimal(request.POST.get("amount"))
        phone = request.POST.get("phone")
        
        # FIXED: Use 'phone' argument
        result = initiate_stk_push(
            user=request.user,
            chama=loan.loan_chama,
            phone=phone,
            amount=amount,
            transaction_type="loan_repayment",
            internal_ref=f"LOANREPAY-{loan.id}"
        )
        
        if result.get("success"):
            messages.success(request, "Repayment initiated via M-Pesa.")
        else:
            messages.error(request, "Failed to initiate payment.")
            
    return redirect("finance:loan_detail", loan_id=loan.id)

@login_required
def send_loan_reminder(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id)
    membership = get_object_or_404(Membership, membership_user=request.user, membership_chama=loan.loan_chama)

    if membership.membership_role not in ["treasurer", "admin"]:
        return HttpResponseForbidden("Unauthorized")

    send_chama_notification(
        chama=loan.loan_chama,
        recipients=[loan.loan_user],
        title="Loan Repayment Reminder",
        message=f"Please repay your outstanding loan balance of KES {loan.loan_outstanding_balance}.",
        sender=request.user,
        n_type="reminder",
        priority="high"
    )
    messages.success(request, "Reminder sent to borrower.")
    return redirect("finance:loan_detail", loan_id=loan.id)


# ==========================================
#  4. PENALTIES
# ==========================================

@login_required
def list_penalties(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    
    try:
        membership = Membership.objects.get(membership_user=request.user, membership_chama=chama)
        current_role = str(membership.membership_role).lower()
    except Membership.DoesNotExist:
        messages.error(request, "You are not a member of this Chama.")
        return redirect('dashboard:dashboard')

    if current_role in ['treasurer', 'admin', 'chairperson']:
        penalties = Penalty.objects.filter(penalty_chama=chama).order_by("-penalty_created_at")
    else:
        penalties = Penalty.objects.filter(penalty_chama=chama, penalty_user=request.user).order_by("-penalty_created_at")
    
    raw_members = Membership.objects.filter(
        membership_chama=chama, 
        membership_status='active'
    ).select_related('membership_user').order_by('membership_user__user_first_name')

    member_list = []
    for m in raw_members:
        name = m.membership_user.get_full_name().strip()
        if not name:
            name = m.membership_user.user_email
        member_list.append({'id': m.membership_user.id, 'name': name})

    penalties_page = paginate_queryset(penalties, request.GET.get("page"))

    return render(request, "finance/list_penalties.html", {
        "chama": chama,
        "membership": membership,
        "current_role": current_role,
        "penalties": penalties_page,
        "members": member_list,
    })

@login_required
def create_penalty(request, chama_id):
    chama = get_object_or_404(Chama, id=chama_id)
    
    if request.method == "POST":
        try:
            user_id = request.POST.get('user_id')
            amount = Decimal(request.POST.get('amount'))
            reason = request.POST.get('reason')

            p = Penalty.objects.create(
                penalty_user_id=user_id,
                penalty_chama=chama,
                penalty_amount=amount,
                penalty_reason=reason
            )

            send_chama_notification(
                chama=chama,
                recipients=[p.penalty_user],
                title="Penalty Created",
                message=f"A penalty of KES {amount} was applied to your account: reason",
                sender=request.user,
                n_type="penalty",
                related_penalty=p
            )

            messages.success(request, f"Penalty created for {p.penalty_user.get_full_name()}")
        except Exception as e:
            messages.error(request, f"Error creating penalty: {str(e)}")
            
    return redirect("finance:list_penalties", chama_id=chama.id)

@login_required
def edit_penalty(request, penalty_id):
    penalty = get_object_or_404(Penalty, id=penalty_id)
    if request.method == "POST":
        penalty.penalty_amount = Decimal(request.POST.get('amount'))
        penalty.penalty_reason = request.POST.get('reason')
        penalty.save()
        messages.success(request, "Penalty updated.")
    return redirect('finance:list_penalties', chama_id=penalty.penalty_chama.id)

@login_required
def delete_penalty(request, penalty_id):
    penalty = get_object_or_404(Penalty, id=penalty_id)
    chama_id = penalty.penalty_chama.id
    penalty.delete()
    messages.success(request, "Penalty deleted.")
    return redirect('finance:list_penalties', chama_id=chama_id)

@login_required
def send_penalty_reminder(request, penalty_id):
    penalty = get_object_or_404(Penalty, id=penalty_id)
    send_chama_notification(
        chama=penalty.penalty_chama,
        recipients=[penalty.penalty_user],
        title="Penalty Payment Reminder",
        message=f"Reminder: You have an outstanding penalty of KES {penalty.penalty_amount} for '{penalty.penalty_reason}'. Please pay via the app.",
        sender=request.user,
        n_type="reminder",
        related_penalty=penalty
    )
    messages.success(request, f"Reminder sent to {penalty.penalty_user.get_full_name()}.")
    return redirect('finance:list_penalties', chama_id=penalty.penalty_chama.id)


# ==========================================
#  5. DARAJA / TRANSACTIONS
# ==========================================

@login_required
def query_transaction_page(request):
    return render(request, "finance/query_transaction.html")
# In finance/views.py

@login_required
def query_transaction_api(request, checkout_id):
    # 1. Setup Request
    Timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    query_url = "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query"
    BusinessShortCode = settings.MPESA_SHORTCODE
    passkey = settings.MPESA_PASSKEY
    Password = base64.b64encode(f"{BusinessShortCode}{passkey}{Timestamp}".encode()).decode()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token()}"
    }
    payload = {
        "BusinessShortCode": BusinessShortCode,
        "Password": Password,
        "Timestamp": Timestamp,
        "CheckoutRequestID": checkout_id
    }
    
    try:
        # 2. Query Daraja
        response = requests.post(query_url, json=payload, headers=headers)
        data = response.json()
        
        # 3. CRITICAL: Parse Result & Update DB
        result_code = str(data.get('ResultCode'))
        result_desc = data.get('ResultDesc') or data.get('ResponseDescription', '')

        tx = Transaction.objects.filter(transaction_checkout_request_id=checkout_id).first()
        
        if tx:
            # --- Handle Different Statuses ---
            if result_code == '0':
                tx.transaction_status = 'success'
                if 'CallbackMetadata' in data:
                    items = data['CallbackMetadata'].get('Item', [])
                    for item in items:
                        if item.get('Name') == 'MpesaReceiptNumber':
                            tx.transaction_mpesa_receipt = item.get('Value')
                        if item.get('Name') == 'PhoneNumber':
                            tx.transaction_phone_number = item.get('Value')
                            
            elif result_code == '1032':
                 # THIS IS THE MISSING PART FOR CANCELLATION
                 tx.transaction_status = 'cancelled'
                 tx.failure_reason = "Cancelled by user"
                 
            elif result_code not in ['0', '1032']:
                 # Any other code (e.g. 1037 Timeout, 1 Insufficient Funds) is a failure
                 tx.transaction_status = 'failed'
                 tx.failure_reason = result_desc
            
            tx.save()
            
            # 4. Force Update the Contribution/Loan Record
            update_related_record(tx)

        # 5. Prepare Response for Frontend
        payer_name = "Unknown Member"
        local_amount = "-"
        local_phone = "-"
        local_receipt = "-"
        local_date = "-"

        if tx:
            if tx.transaction_user:
                full_name = f"{tx.transaction_user.user_first_name} {tx.transaction_user.user_last_name}".strip()
                payer_name = full_name if full_name else tx.transaction_user.user_email
            
            local_amount = str(tx.transaction_amount)
            local_phone = tx.transaction_phone_number
            local_receipt = tx.transaction_mpesa_receipt or "Pending"
            local_date = tx.transaction_created_at.strftime("%d/%m/%Y %H:%M")

        data['LocalPayerName'] = payer_name
        data['LocalAmount'] = local_amount
        data['LocalPhone'] = local_phone
        data['LocalReceipt'] = local_receipt
        data['LocalDate'] = local_date
        
        # Inject our interpreted status so the badge shows correctly immediately
        data['LocalStatus'] = tx.transaction_status if tx else "unknown"

        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse({"ResultCode": "1", "ResultDesc": str(e)})

@login_required
def query_transaction_api(request, checkout_id):
    # 1. Setup Request
    Timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    query_url = "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query"
    BusinessShortCode = settings.MPESA_SHORTCODE
    passkey = settings.MPESA_PASSKEY
    Password = base64.b64encode(f"{BusinessShortCode}{passkey}{Timestamp}".encode()).decode()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token()}"
    }
    payload = {
        "BusinessShortCode": BusinessShortCode,
        "Password": Password,
        "Timestamp": Timestamp,
        "CheckoutRequestID": checkout_id
    }
    
    try:
        # 2. Query Daraja
        response = requests.post(query_url, json=payload, headers=headers)
        data = response.json()
        
        # 3. Inject Local Data (Corrected for Custom User Model)
        tx = Transaction.objects.filter(transaction_checkout_request_id=checkout_id).first()
        
        payer_name = "Unknown Member"
        local_amount = "-"
        local_phone = "-"
        local_date = "-"
        local_receipt = "-"

        if tx:
            def get_name_from_user(u):
                # Try First + Last Name
                full_name = f"{u.user_first_name} {u.user_last_name}".strip()
                if full_name:
                    return full_name
                # Fallback to Email (Since username is None)
                return u.user_email

            # Attempt 1: Get from Transaction User
            if tx.transaction_user:
                payer_name = get_name_from_user(tx.transaction_user)

            # Attempt 2: If still unknown, check related Contribution
            if payer_name == "Unknown Member":
                from .models import Contribution
                # Find contribution with this checkout ID
                contrib = Contribution.objects.filter(contribution_reference=checkout_id).first()
                if contrib and contrib.contribution_user:
                    payer_name = get_name_from_user(contrib.contribution_user)

            # Populate other details
            local_amount = str(tx.transaction_amount)
            local_phone = tx.transaction_phone_number
            local_receipt = tx.transaction_mpesa_receipt or "Pending"
            local_date = tx.transaction_created_at.strftime("%d/%m/%Y %H:%M")

        # Inject into response
        data['LocalPayerName'] = payer_name
        data['LocalAmount'] = local_amount
        data['LocalPhone'] = local_phone
        data['LocalReceipt'] = local_receipt
        data['LocalDate'] = local_date

        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse({"ResultCode": "1", "ResultDesc": str(e)})
    
@csrf_exempt
def stk_callback(request):
    if request.method != "POST":
        return HttpResponse("Invalid request")

    try:
        data = json.loads(request.body.decode("utf-8"))
        stk_data = data.get("Body", {}).get("stkCallback", {})
        
        ResultCode = stk_data.get("ResultCode")
        CheckoutRequestID = stk_data.get("CheckoutRequestID")
        
        tx = Transaction.objects.filter(transaction_checkout_request_id=CheckoutRequestID).first()
        if tx:
            tx.transaction_status = "success" if ResultCode == 0 else "failed"
            if ResultCode == 0:
                metadata = stk_data.get("CallbackMetadata", {}).get("Item", [])
                for item in metadata:
                    if item.get("Name") == "Amount": 
                        tx.transaction_amount = item.get("Value")
                    if item.get("Name") == "MpesaReceiptNumber": 
                        tx.transaction_mpesa_receipt = item.get("Value")
                    if item.get("Name") == "PhoneNumber": 
                        tx.transaction_phone_number = item.get("Value")
            tx.save()
            
            # Update related records if payment was successful
            if ResultCode == 0:
                update_related_record(tx)
            
    except Exception as e:
        print(f"Callback error: {str(e)}")
        return JsonResponse({"ResultCode": 1, "ResultDesc": str(e)})

    return JsonResponse({"ResultCode": 0, "ResultDesc": "Callback received"})

def update_related_record(transaction):
    """Update the related Contribution, Penalty, or Loan record based on transaction status"""
    from finance.models import Contribution, Penalty, LoanRepayment, Loan
    from decimal import Decimal
    
    # Get the status from the transaction (success, cancelled, or failed)
    new_status = transaction.transaction_status

    try:
        if transaction.transaction_type == "contribution":
            # Find the pending contribution
            contrib = Contribution.objects.filter(
                contribution_user=transaction.transaction_user,
                contribution_chama=transaction.transaction_chama,
                contribution_reference=transaction.transaction_checkout_request_id
            ).first()
            
            # Fallback search if reference missing
            if not contrib:
                contrib = Contribution.objects.filter(
                    contribution_user=transaction.transaction_user,
                    contribution_chama=transaction.transaction_chama,
                    contribution_status="pending",
                    contribution_amount=Decimal(str(transaction.transaction_amount))
                ).order_by('-contribution_created_at').first()
            
            if contrib:
                contrib.contribution_status = new_status 
                if new_status == "success":
                    contrib.contribution_mpesa_receipt = transaction.transaction_mpesa_receipt
                contrib.save()
                print(f"✅ Updated contribution {contrib.id} to {new_status}")
        
        elif transaction.transaction_type == "penalty":
            if new_status == "success":
                penalty = Penalty.objects.filter(
                    penalty_user=transaction.transaction_user,
                    penalty_chama=transaction.transaction_chama,
                    penalty_paid=False,
                    penalty_amount=float(transaction.transaction_amount)
                ).first()
                if penalty:
                    penalty.penalty_paid = True
                    penalty.save()

        elif transaction.transaction_type == "loan_repayment":
            if new_status == "success":
                loan = Loan.objects.filter(
                    loan_user=transaction.transaction_user,
                    loan_chama=transaction.transaction_chama,
                    loan_status="active"
                ).first()
                
                if loan:
                    repayment = LoanRepayment.objects.create(
                        loan_repayment_loan=loan,
                        loan_repayment_user=transaction.transaction_user,
                        loan_repayment_amount=Decimal(str(transaction.transaction_amount)),
                        loan_repayment_mpesa_receipt=transaction.transaction_mpesa_receipt,
                        loan_repayment_reference=transaction.transaction_checkout_request_id
                    )
                    loan.loan_outstanding_balance -= Decimal(str(transaction.transaction_amount))
                    if loan.loan_outstanding_balance <= 0:
                        loan.loan_status = "completed"
                    loan.save()

    except Exception as e:
        print(f"❌ Error updating related record: {str(e)}")