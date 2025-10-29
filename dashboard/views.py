from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def member_dashboard(request):
    return render(request, "dashboard/member_dashboard.html")

@login_required
def admin_dashboard(request):
    return render(request, "dashboard/admin_dashboard.html")

@login_required
def secretary_dashboard(request):
    return render(request, "dashboard/secretary_dashboard.html")

@login_required
def treasurer_dashboard(request):
    return render(request, "dashboard/treasurer_dashboard.html")

