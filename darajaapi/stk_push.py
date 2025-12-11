import base64
import uuid
from datetime import datetime
from decimal import Decimal
import requests
from django.conf import settings
from darajaapi.models import Transaction
from darajaapi.accesstoken import access_token

def initiate_stk_push(user, chama, phone: str, amount, tx_type: str):
    """
    Initiate M-Pesa STK Push
    Args:
        user: User object
        chama: Chama object
        phone: Phone number (string)
        amount: Amount (Decimal or int)
        tx_type: Transaction type (string)
    """
    try:
        # Convert Decimal/float to int (M-Pesa only accepts integers)
        if isinstance(amount, Decimal):
            amount = int(amount)
        elif isinstance(amount, float):
            amount = int(amount)
        
        # Format phone number to ensure it's in correct format (254...)
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif phone.startswith('+254'):
            phone = phone[1:]
        elif not phone.startswith('254'):
            phone = '254' + phone
        
        processrequest_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        callback_url = "https://vacuous-elva-appauma.ngrok-free.dev/api/mpesa/stk/callback/"
        
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(
            f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}".encode()
        ).decode()
        
        # Generate internal reference
        internal_ref = str(uuid.uuid4())[:12]  # M-Pesa AccountReference max 12 chars
        
        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,  # Now guaranteed to be an integer
            "PartyA": phone,
            "PartyB": settings.MPESA_SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": callback_url,
            "AccountReference": internal_ref,
            "TransactionDesc": f"{tx_type[:17]} pmt"  # Max 20 chars for M-Pesa
        }
        
        headers = {
            "Authorization": f"Bearer {access_token()}",
            "Content-Type": "application/json",
        }
        
        response = requests.post(processrequest_url, json=payload, headers=headers, timeout=30)
        response_data = response.json()
        
        # Check if request was successful
        if response_data.get("ResponseCode") == "0":
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
                transaction_internal_reference=internal_ref,
            )
            
            return {
                "success": True,
                "CheckoutRequestID": response_data.get("CheckoutRequestID"),
                "MerchantRequestID": response_data.get("MerchantRequestID"),
                "ResponseDescription": response_data.get("ResponseDescription", "STK Push sent"),
                "CustomerMessage": response_data.get("CustomerMessage", "Check your phone")
            }
        else:
            # M-Pesa returned an error
            error_msg = response_data.get("errorMessage") or response_data.get("ResponseDescription", "STK Push failed")
            return {
                "success": False,
                "errorMessage": str(error_msg),  # Convert to string to avoid serialization issues
                "errorCode": response_data.get("errorCode", "Unknown")
            }
    
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "errorMessage": "Request timeout. Please try again."
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "errorMessage": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "errorMessage": f"Error: {str(e)}"
        }