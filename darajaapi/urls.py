from django.urls import path
from darajaapi import views

urlpatterns = [
    path("stk/initiate/<int:chama_id>/", views.initiate_payment, name="initiate_payment"),
    path("stk/callback/", views.stk_callback, name="stk_callback"),
    path("stk/query/<str:checkout_id>/", views.query_transaction, name="query_transaction"),
    path("stk/my-transactions/", views.my_transactions, name="my_transactions"),
]
