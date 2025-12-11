import json
import uuid
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from darajaapi.accesstoken import access_token
from django.conf import settings
from darajaapi.stk_push import initiate_stk_push
from darajaapi.models import Transaction
from chama.models import Chama

# Trigger STK Push from dashboard button
@login_required
def initiate_payment(request, chama_id):
    if request.method == "POST":
        amount = int(request.POST.get("amount"))
        phone = request.POST.get("phone")
        tx_type = request.POST.get("type")  
        chama = get_object_or_404(Chama, id=chama_id)
        user = request.user
        response = initiate_stk_push(user, chama, phone, amount, tx_type)
        return JsonResponse(response)

    return HttpResponse("Invalid request method", status=405)


# Handle Daraja Callback
@csrf_exempt
def stk_callback(request):
    if request.method != "POST":
        return HttpResponse("Invalid request")

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Invalid JSON"}, status=400)

    stk_data = data.get("Body", {}).get("stkCallback", {})
    CheckoutRequestID = stk_data.get("CheckoutRequestID")
    ResultCode = stk_data.get("ResultCode")
    ResultDesc = stk_data.get("ResultDesc")

    # Find transaction
    tx = Transaction.objects.filter(transaction_checkout_request_id=CheckoutRequestID).first()

    if tx:
        # 1. Determine Status
        if ResultCode == 0:
            tx.transaction_status = "success"
            # Extract Metadata
            metadata = stk_data.get("CallbackMetadata", {})
            for item in metadata.get("Item", []):
                if item.get("Name") == "Amount":
                    tx.transaction_amount = item.get("Value")
                elif item.get("Name") == "MpesaReceiptNumber":
                    tx.transaction_mpesa_receipt = item.get("Value")
                elif item.get("Name") == "PhoneNumber":
                    tx.transaction_phone_number = item.get("Value")
        elif ResultCode == 1032:
            tx.transaction_status = "cancelled" 
        else:
            tx.transaction_status = "failed" 

        tx.save()
        update_related_record(tx)

    return JsonResponse({"ResultCode": 0, "ResultDesc": "Callback received"})

def update_related_record(transaction):
    """Update the related Contribution, Penalty, or Loan record based on transaction type"""
    from finance.models import Contribution, Penalty, LoanRepayment, Loan
    from decimal import Decimal
    
    try:
        if transaction.transaction_type == "contribution":
            # Find and update the pending contribution
            contrib = Contribution.objects.filter(
                contribution_user=transaction.transaction_user,
                contribution_chama=transaction.transaction_chama,
                contribution_status="pending",
                contribution_reference=transaction.transaction_checkout_request_id
            ).first()
            
            if not contrib:
                # Fallback: find by amount and user (if reference wasn't set)
                contrib = Contribution.objects.filter(
                    contribution_user=transaction.transaction_user,
                    contribution_chama=transaction.transaction_chama,
                    contribution_status="pending",
                    contribution_amount=Decimal(str(transaction.transaction_amount))
                ).order_by('-contribution_created_at').first()
            
            if contrib:
                contrib.contribution_status = "success"
                contrib.contribution_mpesa_receipt = transaction.transaction_mpesa_receipt
                contrib.contribution_reference = transaction.transaction_checkout_request_id
                contrib.save()
                print(f"✅ Updated contribution {contrib.id} to success")
        
        elif transaction.transaction_type == "penalty":
            # Find and mark penalty as paid
            penalty = Penalty.objects.filter(
                penalty_user=transaction.transaction_user,
                penalty_chama=transaction.transaction_chama,
                penalty_paid=False,
                penalty_amount=float(transaction.transaction_amount)
            ).first()
            
            if penalty:
                penalty.penalty_paid = True
                penalty.save()
                print(f"✅ Marked penalty {penalty.id} as paid")
        
        elif transaction.transaction_type == "loan_repayment":
            # Find active loan for this user
            loan = Loan.objects.filter(
                loan_user=transaction.transaction_user,
                loan_chama=transaction.transaction_chama,
                loan_status="active"
            ).first()
            
            if loan:
                # Create loan repayment record
                repayment = LoanRepayment.objects.create(
                    loan_repayment_loan=loan,
                    loan_repayment_user=transaction.transaction_user,
                    loan_repayment_amount=Decimal(str(transaction.transaction_amount)),
                    loan_repayment_mpesa_receipt=transaction.transaction_mpesa_receipt,
                    loan_repayment_reference=transaction.transaction_checkout_request_id
                )
                
                # Update loan outstanding balance
                loan.loan_outstanding_balance -= Decimal(str(transaction.transaction_amount))
                if loan.loan_outstanding_balance <= 0:
                    loan.loan_status = "completed"
                loan.save()
                print(f"✅ Created loan repayment {repayment.id}, updated loan {loan.id}")
        
        elif transaction.transaction_type == "registration_fee":
            # Handle registration fee if needed
            print(f"✅ Registration fee payment recorded: {transaction.transaction_mpesa_receipt}")
    
    except Exception as e:
        print(f"❌ Error updating related record: {str(e)}")


# List User Transactions
@login_required
def my_transactions(request):
    txs = Transaction.objects.filter(transaction_user=request.user).order_by("-transaction_created_at")
    data = [
        {
            "amount": str(tx.transaction_amount),
            "type": tx.transaction_type,
            "status": tx.transaction_status,
            "receipt": tx.transaction_mpesa_receipt,
            "internal_ref": tx.transaction_internal_reference, 
            "created_at": tx.transaction_created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for tx in txs
    ]
    return JsonResponse({"transactions": data})