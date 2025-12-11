from django.urls import path
from . import views

app_name = 'darajaapi'

urlpatterns = [
    path('initiate/<int:chama_id>/', views.initiate_payment, name='initiate_payment'),
    path('stk/callback/', views.stk_callback, name='stk_callback'),
    path('my-transactions/', views.my_transactions, name='my_transaction'),
]