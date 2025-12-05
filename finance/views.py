from decimal import Decimal
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from darajaapi.models import Transaction
from darajaapi.views import initiate_stk_push
from chama.models import Chama, Membership
from .models import (
    Contribution, ContributionCycle, Penalty, Loan,
    LoanRepayment, CONTRIBUTION_TYPE_CHOICES, CYCLE_TYPE_CHOICES
)

from common.utils import (
    paginate_queryset, update_status, send_chama_notification
)

# -------------------------
# CONTRIBUTIONS
# -------------------------

@login_required
def create_contribution(request, chama_id):
    chama = get_object_or_404(Chama, chama_id=chama_id)
    membership = get_object_or_404(Membership,
        membership_user=request.user, membership_chama=chama)

    active_cycles = ContributionCycle.objects.filter(
        cycle_chama=chama,
        cycle_status='open',
        cycle_deadline__gte=timezone.now().date()
    )

    if request.method == 'POST':
        try:
            cycle = ContributionCycle.objects.get(id=request.POST.get('cycle_id')) if request.POST.get('cycle_id') else None
            amount = Decimal(request.POST.get('amount'))
            phone = request.POST.get('phone')
            ctype = request.POST.get('contribution_type')

            if cycle and amount < cycle.cycle_amount_required and ctype == "contribution":
                messages.error(request, f"Amount is below the required {cycle.cycle_amount_required}.")
                return redirect("finance:create_contribution", chama_id=chama_id)

            result = initiate_stk_push(
                phone_number=phone,
                amount=amount,
                account_reference=f"{getattr(chama, 'chama_paybill_account_number', chama.id)}-{ctype}",
                transaction_desc=ctype,
                user=request.user,
                chama=chama,
                transaction_type=ctype
            )

            if not result.get("success"):
                messages.error(request, result.get("message") or "Payment initiation failed.")
                return redirect("finance:create_contribution", chama_id=chama_id)

            contribution = Contribution.objects.create(
                contribution_user=request.user,
                contribution_chama=chama,
                contribution_cycle=cycle,
                contribution_amount=amount,
                contribution_type=ctype,
                contribution_phone=phone,
                contribution_status="pending",
                contribution_reference=result.get("checkout_request_id"),
                contribution_time=timezone.now()
            )

            # Notify user
            send_chama_notification(
                chama=chama,
                recipients=[request.user],
                title="Payment Initiated",
                message=f"An M-Pesa payment of KSh {amount} was initiated for {chama.chama_name}. Please complete the STK prompt.",
                sender=request.user,
                n_type="payment",
                related_contribution=contribution
            )

            # Notify treasurers
            treasurers = Membership.objects.filter(
                membership_chama=chama,
                membership_role='treasurer',
                membership_status='active'
            ).select_related('membership_user')
            treasurer_users = [m.membership_user for m in treasurers]
            if treasurer_users:
                send_chama_notification(
                    chama=chama,
                    recipients=treasurer_users,
                    title="Pending Contribution",
                    message=f"{request.user.get_full_name()} initiated a payment of KSh {amount} (pending).",
                    sender=request.user,
                    n_type="payment",
                    related_contribution=contribution
                )

            messages.success(request, "STK push sent! Please complete the payment on your phone.")
            return redirect("finance:list_contributions", chama_id=chama_id)

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, "finance/create_contribution.html", {
        "chama": chama,
        "membership": membership,
        "active_cycles": active_cycles,
        "contribution_types": CONTRIBUTION_TYPE_CHOICES
    })


@login_required
def list_contributions(request, chama_id):
    chama = get_object_or_404(Chama, chama_id=chama_id)
    membership = get_object_or_404(Membership,
        membership_user=request.user, membership_chama=chama)

    contributions = Contribution.objects.filter(
        contribution_chama=chama
    ) if membership.membership_role == "treasurer" else Contribution.objects.filter(
        contribution_chama=chama, contribution_user=request.user
    )

    if request.GET.get("status"):
        contributions = contributions.filter(contribution_status=request.GET["status"])

    contributions = contributions.select_related("contribution_user", "contribution_cycle")\
        .order_by("-contribution_created_at")

    contributions_page = paginate_queryset(contributions, request.GET.get("page"))

    return render(request, "finance/list_contributions.html", {
        "chama": chama,
        "membership": membership,
        "contributions": contributions_page,
        "cycles": ContributionCycle.objects.filter(cycle_chama=chama)
    })

# -------------------------
# CONTRIBUTION CYCLE VIEWS
# -------------------------

@login_required
def list_cycles(request, chama_id):
    chama = get_object_or_404(Chama, chama_id=chama_id)
    membership = get_object_or_404(Membership,
        membership_user=request.user, membership_chama=chama)

    cycles = ContributionCycle.objects.filter(cycle_chama=chama)\
        .order_by("-cycle_created_at")

    for c in cycles:
        c.total_contributed = Contribution.objects.filter(
            contribution_cycle=c, contribution_status="success"
        ).aggregate(Sum("contribution_amount"))["contribution_amount__sum"] or Decimal('0')

    return render(request, "finance/list_cycles.html", {
        "chama": chama,
        "membership": membership,
        "cycles": cycles,
        "cycle_types": CYCLE_TYPE_CHOICES
    })


@login_required
def create_cycle(request, chama_id):
    chama = get_object_or_404(Chama, chama_id=chama_id)
    membership = get_object_or_404(Membership,
        membership_user=request.user, membership_chama=chama)

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

            members = Membership.objects.filter(
                membership_chama=chama, membership_status='active'
            ).select_related('membership_user')
            recipients = [m.membership_user for m in members]

            send_chama_notification(
                chama=chama,
                recipients=recipients,
                title=f"New Cycle: {cycle_name}",
                message=f"A new contribution cycle '{cycle_name}' requiring KSh {cycle_amount} has been created. Deadline: {cycle_deadline}.",
                sender=request.user,
                n_type="reminder"
            )

            messages.success(request, f"Cycle '{cycle_name}' created and members notified.")
            return redirect("finance:cycle_detail", cycle_id=cycle.id)

        except Exception as e:
            messages.error(request, f"Error creating cycle: {str(e)}")

    members = Membership.objects.filter(
        membership_chama=chama, membership_status='active'
    ).select_related('membership_user')

    return render(request, "finance/create_cycle.html", {
        "chama": chama,
        "members": members,
        "cycle_types": CYCLE_TYPE_CHOICES
    })
@login_required
def cycle_detail(request, cycle_id):
    cycle = get_object_or_404(ContributionCycle, id=cycle_id)
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=cycle.cycle_chama
    )

    contributions = Contribution.objects.filter(
        contribution_cycle=cycle
    ).select_related("contribution_user").order_by("-contribution_created_at")

    contributed_ids = contributions.filter(
        contribution_status="success"
    ).values_list("contribution_user", flat=True)

    non_contributors = Membership.objects.filter(
        membership_chama=cycle.cycle_chama,
        membership_status="active"
    ).exclude(membership_user_id__in=contributed_ids)

    return render(request, "finance/cycle_detail.html", {
        "cycle": cycle,
        "membership": membership,
        "contributions": contributions,
        "non_contributors": non_contributors,
    })

def generate_cycle_penalties(cycle):
    """
    Auto-generate penalties for non-contributors in a closed cycle.
    Notifications:
      - send penalty notice to each penalized member
      - send treasurer summary
    """
    contributed_users = Contribution.objects.filter(
        contribution_cycle=cycle,
        contribution_status="success"
    ).values_list("contribution_user_id", flat=True)

    non_contributors = Membership.objects.filter(
        membership_chama=cycle.cycle_chama,
        membership_status="active"
    ).exclude(membership_user_id__in=contributed_users)

    penalty_amount = cycle.cycle_amount_required * Decimal("0.1")  # 10% penalty

    penalized_users = []
    for membership in non_contributors:
        p = Penalty.objects.create(
            penalty_user=membership.membership_user,
            penalty_chama=cycle.cycle_chama,
            penalty_amount=penalty_amount,
            penalty_reason=f"Missed contribution for cycle: {cycle.cycle_name}"
        )
        penalized_users.append(membership.membership_user)

        # Notify penalized user
        send_chama_notification(
            chama=cycle.cycle_chama,
            recipients=[membership.membership_user],
            title="Penalty Issued",
            message=f"You have been charged a penalty of KSh {penalty_amount} for missing cycle '{cycle.cycle_name}'.",
            sender=None,
            n_type="penalty",
            related_penalty=p
        )

    # Notify treasurers with a summary
    treasurers = Membership.objects.filter(
        membership_chama=cycle.cycle_chama,
        membership_role="treasurer"
    ).select_related("membership_user")
    treasurer_users = [t.membership_user for t in treasurers]

    if treasurer_users and penalized_users:
        send_chama_notification(
            chama=cycle.cycle_chama,
            recipients=treasurer_users,
            title=f"Penalties Generated for {cycle.cycle_name}",
            message=f"Penalties generated for {len(penalized_users)} member(s).",
            sender=None,
            n_type="penalty"
        )

@login_required
def close_cycle(request, cycle_id):
    cycle = get_object_or_404(ContributionCycle, id=cycle_id)
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=cycle.cycle_chama
    )

    if membership.membership_role not in ["treasurer", "admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")

    if request.method == "POST":
        cycle.cycle_status = "closed"
        cycle.save()

        # Optionally generate penalties
        if request.POST.get("generate_penalties") == "yes":
            generate_cycle_penalties(cycle)

        # Notify all members
        members = Membership.objects.filter(
            membership_chama=cycle.cycle_chama,
            membership_status="active"
        ).select_related("membership_user")
        recipients = [m.membership_user for m in members]

        send_chama_notification(
            chama=cycle.cycle_chama,
            recipients=recipients,
            title=f"Cycle Closed: {cycle.cycle_name}",
            message=f"The cycle '{cycle.cycle_name}' has been closed. Check contributions and penalties in the finance tab.",
            sender=request.user,
            n_type="announcement"
        )

        messages.success(request, f"Cycle '{cycle.cycle_name}' closed and members notified.")
        return redirect("finance:cycle_detail", cycle_id=cycle.id)

    return render(request, "finance/close_cycle.html", {"cycle": cycle})

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

    # Find non‑contributors
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
        messages.info(request, "No non‑contributors to remind.")
        return redirect("finance:cycle_detail", cycle_id=cycle.id)

    send_chama_notification(
        chama=cycle.cycle_chama,
        recipients=recipients,
        title=f"Reminder: {cycle.cycle_name} Due {cycle.cycle_deadline}",
        message=f"Please pay KSh {cycle.cycle_amount_required} for cycle '{cycle.cycle_name}' before {cycle.cycle_deadline}.",
        sender=request.user,
        n_type="reminder",
        priority="high"
    )

    messages.success(request, f"Sent reminders to {len(recipients)} member(s).")
    return redirect("finance:cycle_detail", cycle_id=cycle.id)

@login_required
def list_penalties(request, chama_id):
    chama = get_object_or_404(Chama, chama_id=chama_id)
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=chama
    )

    # Treasurer sees all penalties, members see their own
    qs = Penalty.objects.filter(
        penalty_chama=chama
    ) if membership.membership_role == "treasurer" else Penalty.objects.filter(
        penalty_chama=chama,
        penalty_user=request.user
    )

    penalties_page = paginate_queryset(qs.order_by("-penalty_created_at"), request.GET.get("page"))

    return render(request, "finance/list_penalties.html", {
        "chama": chama,
        "membership": membership,
        "penalties": penalties_page,
    })

@login_required
def create_penalty(request, chama_id):
    chama = get_object_or_404(Chama, chama_id=chama_id)
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=chama
    )

    if membership.membership_role not in ['treasurer', 'admin', 'secretary']:
        return HttpResponseForbidden("Unauthorized")

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

            # Notify penalized user
            send_chama_notification(
                chama=chama,
                recipients=[p.penalty_user],
                title="Penalty Created",
                message=f"A penalty of KSh {amount} was applied to your account: {reason}",
                sender=request.user,
                n_type="penalty",
                related_penalty=p
            )

            messages.success(request, f"Penalty created for {p.penalty_user.get_full_name()}")
            return redirect("finance:list_penalties", chama_id=chama_id)

        except Exception as e:
            messages.error(request, f"Error creating penalty: {str(e)}")

    members = Membership.objects.filter(
        membership_chama=chama,
        membership_status='active'
    ).select_related('membership_user')

    return render(request, "finance/create_penalty.html", {
        "chama": chama,
        "members": members
    })

@login_required
def list_loans(request, chama_id):
    chama = get_object_or_404(Chama, chama_id=chama_id)
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=chama
    )

    # Treasurer sees all loans, members see their own
    loans = Loan.objects.filter(
        loan_chama=chama
    ) if membership.membership_role == "treasurer" else Loan.objects.filter(
        loan_chama=chama,
        loan_user=request.user
    )

    loans = loans.order_by("-loan_created_at")

    return render(request, "finance/list_loans.html", {
        "chama": chama,
        "membership": membership,
        "loans": loans,
    })

@login_required
def request_loan(request, chama_id):
    chama = get_object_or_404(Chama, chama_id=chama_id)
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=chama
    )

    if request.method == "POST":
        try:
            amount = Decimal(request.POST["amount"])
            rate = Decimal("10.00")  # example interest rate
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

            # Notify treasurers/admins
            treasurers = Membership.objects.filter(
                membership_chama=chama,
                membership_role='treasurer'
            ).select_related('membership_user')
            treasurer_users = [t.membership_user for t in treasurers]

            if treasurer_users:
                send_chama_notification(
                    chama=chama,
                    recipients=treasurer_users,
                    title="Loan Request Submitted",
                    message=f"{request.user.get_full_name()} requested a loan of KSh {amount}. Review and approve/reject in Loans.",
                    sender=request.user,
                    n_type="loan",
                    related_loan=loan
                )

            messages.success(request, "Loan request submitted! Treasurer notified.")
            return redirect("finance:loan_detail", loan_id=loan.id)

        except Exception as e:
            messages.error(request, f"Error requesting loan: {str(e)}")

    return render(request, "finance/request_loan.html", {
        "chama": chama,
        "membership": membership
    })

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from chama.models import Membership
from .models import Loan, LoanRepayment
from django.db.models import Sum

@login_required
def loan_detail(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id)
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=loan.loan_chama
    )

    repayments = LoanRepayment.objects.filter(
        loan_repayment_loan=loan
    ).order_by("-loan_repayment_time")

    total_repaid = repayments.aggregate(Sum("loan_repayment_amount"))[
        "loan_repayment_amount__sum"
    ] or 0

    return render(request, "finance/loan_detail.html", {
        "loan": loan,
        "membership": membership,
        "total_repaid": total_repaid,
        "repayments": repayments,
    })

@login_required
def approve_loan(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id)
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=loan.loan_chama
    )

    if membership.membership_role != "treasurer":
        return HttpResponseForbidden("Unauthorized")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            loan.loan_status = "approved"
            loan.save()

            send_chama_notification(
                chama=loan.loan_chama,
                recipients=[loan.loan_user],
                title="Loan Approved",
                message=f"Your loan request (KSh {loan.loan_amount}) has been approved.",
                sender=request.user,
                n_type="loan",
                related_loan=loan
            )
            messages.success(request, "Loan approved and borrower notified.")

        elif action == "reject":
            loan.loan_status = "rejected"
            loan.save()
            reason = request.POST.get("rejection_reason", "No reason provided")

            send_chama_notification(
                chama=loan.loan_chama,
                recipients=[loan.loan_user],
                title="Loan Rejected",
                message=f"Your loan request was rejected. Reason: {reason}",
                sender=request.user,
                n_type="loan",
                related_loan=loan
            )
            messages.info(request, "Loan rejected and borrower notified.")

    return redirect("finance:loan_detail", loan_id=loan.id)

@login_required
def disburse_loan(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, loan_status='approved')
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=loan.loan_chama
    )

    if membership.membership_role != "treasurer":
        return HttpResponseForbidden("Unauthorized")

    if request.method == "POST":
        reference = request.POST.get("reference", f"LOAN-{loan.id}")
        loan.loan_status = "active"
        loan.loan_reference = reference
        loan.save()

        # Notify borrower
        send_chama_notification(
            chama=loan.loan_chama,
            recipients=[loan.loan_user],
            title="Loan Disbursed",
            message=f"Your loan of KSh {loan.loan_amount} has been disbursed. Reference: {reference}",
            sender=request.user,
            n_type="loan",
            related_loan=loan
        )

        messages.success(request, "Loan disbursed and borrower notified.")
        return redirect("finance:loan_detail", loan_id=loan.id)

    return render(request, "finance/disburse_loan.html", {
        "loan": loan,
        "chama": loan.loan_chama
    })

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from decimal import Decimal
from chama.models import Membership
from .models import Loan, LoanRepayment
from darajaapi.views import initiate_stk_push
from common.utils import send_chama_notification

@login_required
def repay_loan(request, loan_id):
    """
    Member repays a loan via M-Pesa STK push.
    Notifications:
      - notify member that repayment was initiated
      - notify treasurer(s) that repayment is pending
    """
    loan = get_object_or_404(Loan, id=loan_id, loan_user=request.user, loan_status='active')

    if request.method == "POST":
        amount = Decimal(request.POST.get("amount"))
        phone = request.POST.get("phone")

        if amount > loan.loan_outstanding_balance:
            messages.error(request, "Amount exceeds outstanding balance.")
            return redirect("finance:loan_detail", loan_id=loan.id)

        result = initiate_stk_push(
            phone_number=phone,
            amount=amount,
            account_reference=f"{loan.loan_chama.chama_id}-LOAN-{loan.id}",
            transaction_desc="Loan Repayment",
            user=request.user,
            chama=loan.loan_chama,
            transaction_type="loan_repayment"
        )

        if not result.get("success"):
            messages.error(request, result.get("message") or "Payment initiation failed.")
            return redirect("finance:loan_detail", loan_id=loan.id)

        # Create a pending repayment record (final confirmation handled in callback)
        LoanRepayment.objects.create(
            loan_repayment_loan=loan,
            loan_repayment_user=request.user,
            loan_repayment_amount=amount,
            loan_repayment_mpesa_receipt=None,
        )

        # Notify member
        send_chama_notification(
            chama=loan.loan_chama,
            recipients=[request.user],
            title="Loan Repayment Initiated",
            message=f"You initiated a repayment of KSh {amount} for loan {loan.id}. Complete the M-Pesa prompt.",
            sender=request.user,
            n_type="payment",
            related_loan=loan
        )

        # Notify treasurers
        treasurers = Membership.objects.filter(
            membership_chama=loan.loan_chama,
            membership_role="treasurer"
        ).select_related("membership_user")
        treasurer_users = [t.membership_user for t in treasurers]

        if treasurer_users:
            send_chama_notification(
                chama=loan.loan_chama,
                recipients=treasurer_users,
                title="Loan Repayment Pending",
                message=f"{request.user.get_full_name()} initiated a loan repayment of KSh {amount}. Awaiting confirmation.",
                sender=request.user,
                n_type="payment",
                related_loan=loan
            )

        messages.success(request, "STK push sent for loan repayment.")
        return redirect("finance:loan_detail", loan_id=loan.id)

    return render(request, "finance/repay_loan.html", {
        "loan": loan,
        "chama": loan.loan_chama
    })

@login_required
def send_loan_reminder(request, loan_id):
    """
    Treasurer/admin can send a reminder to a borrower about an active loan.
    This is a manual endpoint triggered by a 'Send Reminder' button in the UI.
    """
    loan = get_object_or_404(Loan, id=loan_id)
    membership = get_object_or_404(
        Membership,
        membership_user=request.user,
        membership_chama=loan.loan_chama
    )

    if membership.membership_role not in ["treasurer", "admin", "secretary"]:
        return HttpResponseForbidden("Unauthorized")

    borrower = loan.loan_user

    send_chama_notification(
        chama=loan.loan_chama,
        recipients=[borrower],
        title=f"Reminder: Loan {loan.id} Repayment Due",
        message=f"Please repay your loan of KSh {loan.loan_amount}. Outstanding balance: KSh {loan.loan_outstanding_balance}.",
        sender=request.user,
        n_type="reminder",
        priority="high",
        related_loan=loan
    )

    messages.success(request, f"Reminder sent to {borrower.get_full_name()}.")
    return redirect("finance:loan_detail", loan_id=loan.id)


# -------------------------
# Penalties, Loans, Reminders
# -------------------------
# (All penalty/loan functions remain the same, but replace direct Notification creation
# with send_chama_notification from common.utils, and use paginate_queryset for lists.)
