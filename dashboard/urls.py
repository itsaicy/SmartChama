from django.urls import path
from dashboard.dashboard_views import (
    dashboard, switch_role, member_dashboard, admin_dashboard,
    secretary_dashboard, treasurer_dashboard, dashboard_search,
    assign_role, edit_member, delete_member 
    # REMOVED: update_profile_picture from imports
)
from dashboard.report_views import download_financial_report, download_full_report

app_name = "dashboard"

urlpatterns = [
    # Main Dashboards
    path("", dashboard, name="dashboard"),
    path("switch/<int:chama_id>/<str:role>/", switch_role, name="switch_role"),
    path("member/", member_dashboard, name="member_dashboard_fallback"),
    path("member/<int:chama_id>/", member_dashboard, name="member_dashboard"),
    path("admin/<int:chama_id>/", admin_dashboard, name="admin_dashboard"),
    path("secretary/<int:chama_id>/", secretary_dashboard, name="secretary_dashboard"),
    path("treasurer/<int:chama_id>/", treasurer_dashboard, name="treasurer_dashboard"),
    
    # Reports
    path("report/financial/<int:chama_id>/", download_financial_report, name="financial_report"),
    path("report/full/<int:chama_id>/", download_full_report, name="full_report"),
    
    # Search
    path("chama/<int:chama_id>/search/", dashboard_search, name="dashboard_search"),
    
    # Actions
    path('admin/<int:chama_id>/assign-role/', assign_role, name='assign_role'),
    path('admin/<int:chama_id>/edit/', edit_member, name='edit_member'),
    path('admin/<int:chama_id>/delete/<int:user_id>/', delete_member, name='delete_member'),
    
    

]