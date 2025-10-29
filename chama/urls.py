from django.urls import path
from chama import views

urlpatterns = [
    path('', views.chama_list, name='chama_list'),
    path('create/', views.create_chama, name='create_chama'),
    path('<int:pk>/', views.chama_detail, name='chama_detail'),
    path('<int:pk>/edit/', views.edit_chama, name='edit_chama'),
    path('<int:pk>/join/', views.join_chama, name='join_chama'),
    path('my-chamas/', views.my_chamas, name='my_chamas'),
    path('join-request/<int:request_id>/<str:action>/', views.handle_join_request, name='handle_join_request'),
    path('member/<int:membership_id>/suspend/', views.suspend_member, name='suspend_member'),
]
