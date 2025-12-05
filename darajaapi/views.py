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
        internal_ref = str(uuid.uuid4())
        response = initiate_stk_push(user, chama, phone, amount, tx_type, internal_ref)
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
    MerchantRequestID = stk_data.get("MerchantRequestID")
    CheckoutRequestID = stk_data.get("CheckoutRequestID")
    ResultCode = stk_data.get("ResultCode")
    ResultDesc = stk_data.get("ResultDesc")

    Amount = None
    TransactionID = None
    UserPhone = None
    InternalRef = stk_data.get("AccountReference")  

    metadata = stk_data.get("CallbackMetadata")
    if metadata:
        for item in metadata.get("Item", []):
            if item.get("Name") == "Amount":
                Amount = item.get("Value")
            elif item.get("Name") == "MpesaReceiptNumber":
                TransactionID = item.get("Value")
            elif item.get("Name") == "PhoneNumber":
                UserPhone = item.get("Value")

    tx = Transaction.objects.filter(
        transaction_checkout_request_id=CheckoutRequestID,
        transaction_merchant_request_id=MerchantRequestID,
        transaction_internal_reference=InternalRef
    ).first()

    if tx:
        tx.transaction_amount = Amount
        tx.transaction_phone_number = UserPhone
        tx.transaction_mpesa_receipt = TransactionID
        tx.transaction_status = "success" if ResultCode == 0 else "failed"
        tx.save()

    return JsonResponse({"ResultCode": 0, "ResultDesc": "Callback received"})


# Query Transaction Status
@login_required
def query_transaction(request, checkout_id):
    import base64, datetime, requests

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
    response = requests.post(query_url, json=payload, headers=headers)
    data = response.json()

    return JsonResponse(data)


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
