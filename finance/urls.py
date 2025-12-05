from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [

    # Contribution cycles
    path('cycles/<int:chama_id>/', views.list_cycles, name='list_cycles'),
    path('cycle/create/<int:chama_id>/', views.create_cycle, name='create_cycle'),
    path('cycle/<int:cycle_id>/', views.cycle_detail, name='cycle_detail'),
    path('cycle/<int:cycle_id>/close/', views.close_cycle, name='close_cycle'),
    path('cycle/<int:cycle_id>/remind/', views.send_contribution_reminder, name='send_contribution_reminder'),

    # Contributions
    path('contributions/<int:chama_id>/', views.list_contributions, name='list_contributions'),
    path('contribution/create/<int:chama_id>/', views.create_contribution, name='create_contribution'),

    # Penalties
    path('penalties/<int:chama_id>/', views.list_penalties, name='list_penalties'),
    path('penalty/create/<int:chama_id>/', views.create_penalty, name='create_penalty'),

    # Loans
    path('loans/<int:chama_id>/', views.list_loans, name='list_loans'),
    path('loan/request/<int:chama_id>/', views.request_loan, name='request_loan'),
    path('loan/<int:loan_id>/', views.loan_detail, name='loan_detail'),
    path('loan/<int:loan_id>/approve/', views.approve_loan, name='approve_loan'),
    path('loan/<int:loan_id>/disburse/', views.disburse_loan, name='disburse_loan'),
    path('loan/<int:loan_id>/repay/', views.repay_loan, name='repay_loan'),
    path('loan/<int:loan_id>/remind/', views.send_loan_reminder, name='send_loan_reminder'),
    
]
