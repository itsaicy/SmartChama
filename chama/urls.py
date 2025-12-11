from django.urls import path
from chama import views

app_name = 'chama'

urlpatterns = [
    # Chama List & Detail
    path('', views.chama_list, name='chama_list'),
    path('<int:pk>/', views.chama_detail, name='chama_detail'),
    
    # Chama Management
    path('create/', views.create_chama, name='create_chama'),
    path('<int:pk>/edit/', views.edit_chama, name='edit_chama'),
    path('my-chamas/', views.my_chamas, name='my_chamas'),
    
    # Join Chama
    path('<int:pk>/join/', views.join_chama, name='join_chama'),
    
    # Join Requests
    path('<int:pk>/join-requests/', views.join_requests, name='join_requests'),
    path('join-request/<int:request_id>/accept/', views.accept_request, name='accept_request'),
    path('join-request/<int:request_id>/reject/', views.reject_request, name='reject_request'),
    
    # Member Management - CORE PAGES
    path('<int:pk>/manage-members/', views.manage_members, name='manage_members'),
    
    # Member Actions
    path('<int:chama_id>/add-member/', views.add_member_to_chama, name='add_member_to_chama'),
    path('<int:chama_id>/edit-member/', views.edit_member_details, name='edit_member_details'),
    path('<int:chama_id>/remove-member/<int:user_id>/', views.remove_member, name='remove_member'),
    path('<int:chama_id>/assign-role/<int:user_id>/', views.assign_role, name='assign_role'),
    path('<int:chama_id>/demote-member/<int:user_id>/', views.demote_member, name='demote_member'),
]