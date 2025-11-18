import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings

consumerKey = settings.MPESA_CONSUMER_KEY
consumerSecret = settings.MPESA_CONSUMER_SECRET

access_token_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
headers = {"Content-Type": "application/json; charset=utf8"}

response = requests.get(
    access_token_url,
    headers=headers,
    auth=HTTPBasicAuth(consumerKey, consumerSecret)
)

result = response.json()

# same as: echo $result->access_token
print(result["access_token"])
