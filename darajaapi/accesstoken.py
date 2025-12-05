import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings

def access_token():
    consumerKey = settings.MPESA_CONSUMER_KEY
    consumerSecret = settings.MPESA_CONSUMER_SECRET
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    headers = {"Content-Type": "application/json; charset=utf8"}
    response = requests.get(
        url,
        headers=headers,
        auth=HTTPBasicAuth(consumerKey, consumerSecret)
    )

    return response.json()["access_token"]
