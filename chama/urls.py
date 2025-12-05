from django.urls import path
from chama import views

urlpatterns = [
    path('', views.chama_list, name='chama_list'),
    path('create/', views.create_chama, name='create_chama'),
    path('<int:pk>/', views.chama_detail, name='chama_detail'),
    path('<int:pk>/edit/', views.edit_chama, name='edit_chama'),
    path('<int:pk>/join/', views.join_chama, name='join_chama'),
    path('<int:pk>/join-requests/', views.join_requests, name='join_requests'),
    path('my-chamas/', views.my_chamas, name='my_chamas'),
    path('join-request/<int:request_id>/accept/', views.accept_request, name='accept_request'),
    path('join-request/<int:request_id>/reject/', views.reject_request, name='reject_request'),
    path('<int:chama_id>/remove-member/<int:user_id>/', views.remove_member, name='remove_member'),
    path('<int:chama_id>/manage-members/', views.manage_members, name='manage_members'),
    path('assign-role/', views.assign_role, name='assign_role'),
    path('join-request/<int:request_id>/<str:action>/', views.handle_join_request, name='handle_join_request'),
]

