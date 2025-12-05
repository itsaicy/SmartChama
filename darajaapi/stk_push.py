import base64
import uuid
from datetime import datetime
import requests
from django.conf import settings
from darajaapi.models import Transaction
from darajaapi.accesstoken import access_token

def initiate_stk_push(user, chama, phone: str, amount: int, tx_type: str):
    processrequest_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    callback_url = "https://vacuous-elva-appauma.ngrok-free.dev/api/mpesa/stk/callback/"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}".encode()
    ).decode()

    # 🔹 Generate internal reference
    internal_ref = str(uuid.uuid4())

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": callback_url,
        "AccountReference": internal_ref,   # 🔹 use internal reference here
        "TransactionDesc": f"{tx_type} payment"
    }

    headers = {
        "Authorization": f"Bearer {access_token()}",
        "Content-Type": "application/json",
    }

    response = requests.post(processrequest_url, json=payload, headers=headers)
    response_data = response.json()

    # Save pending transaction
    Transaction.objects.create(
        transaction_user=user,
        transaction_chama=chama,
        transaction_phone_number=phone,
        transaction_amount=amount,
        transaction_type=tx_type,
        transaction_status="pending",
        transaction_merchant_request_id=response_data.get("MerchantRequestID"),
        transaction_checkout_request_id=response_data.get("CheckoutRequestID"),
        transaction_internal_reference=internal_ref,   # 🔹 store it
    )

    return response_data
