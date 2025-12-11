from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('<int:chama_id>/cycles/', views.list_cycles, name='list_cycles'),
    path('<int:chama_id>/cycles/create/', views.create_cycle, name='create_cycle'),
    path('cycle/<int:cycle_id>/', views.cycle_detail, name='cycle_detail'),
    path('cycle/<int:cycle_id>/close/', views.close_cycle, name='close_cycle'),
    path('cycle/<int:cycle_id>/edit/', views.edit_cycle, name='edit_cycle'),
    path('cycle/<int:cycle_id>/delete/', views.delete_cycle, name='delete_cycle'),
    path('cycle/<int:cycle_id>/remind/', views.send_contribution_reminder, name='send_contribution_reminder'),
    path('<int:chama_id>/contributions/', views.list_contributions, name='list_contributions'),
    path('<int:chama_id>/contributions/all/', views.chama_all_contributions, name='chama_all_contributions'),
    path('<int:chama_id>/contributions/create/', views.create_contribution, name='create_contribution'),
    path('check-contribution/<int:contribution_id>/', views.check_contribution_status, name='check_contribution_status'),
    path('member/<int:user_id>/dues/', views.member_dues, name='member_dues'),
    path('<int:chama_id>/outstanding-dues/', views.chama_outstanding_dues, name='chama_outstanding_dues'),
    path('member/<int:user_id>/remind/', views.remind_member_debt, name='remind_member_debt'),
    path('<int:chama_id>/loans/', views.list_loans, name='list_loans'),
    path('<int:chama_id>/loans/request/', views.request_loan, name='request_loan'),
    path('loan/<int:loan_id>/', views.loan_detail, name='loan_detail'),
    path('loan/<int:loan_id>/approve/', views.approve_loan, name='approve_loan'),
    path('loan/<int:loan_id>/disburse/', views.disburse_loan, name='disburse_loan'),
    path('loan/<int:loan_id>/repay/', views.repay_loan, name='repay_loan'),
    path('loan/<int:loan_id>/remind/', views.send_loan_reminder, name='send_loan_reminder'),
    path('<int:chama_id>/penalties/', views.list_penalties, name='list_penalties'),
    path('<int:chama_id>/penalties/create/', views.create_penalty, name='create_penalty'),
    path('penalty/edit/<int:penalty_id>/', views.edit_penalty, name='edit_penalty'),
    path('penalty/delete/<int:penalty_id>/', views.delete_penalty, name='delete_penalty'),
    path('penalty/<int:penalty_id>/remind/', views.send_penalty_reminder, name='send_penalty_reminder'),
    path('transaction/query/', views.query_transaction_page, name='query_transaction_page'),
    path('stk/query/<str:checkout_id>/', views.query_transaction_api, name='query_transaction_api'),
    path('stk/callback/', views.stk_callback, name='stk_callback'),
]