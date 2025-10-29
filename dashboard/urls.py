from django.urls import path
from dashboard.views import treasurer_dashboard, secretary_dashboard,admin_dashboard,\
member_dashboard

urlpatterns = [
    path('member/dashboard/', member_dashboard, name='member_dashboard'),
    path('admin/dashboard/', admin_dashboard, name='admin_dashboard'),
    path('secretary/dashboard/', secretary_dashboard, name='secretary_dashboard'),
    path('treasurer/dashboard/', treasurer_dashboard, name='treasurer_dashboard'),
]
