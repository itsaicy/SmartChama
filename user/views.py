from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from chama.utils import get_user_dashboard_redirect
from user.forms import RegistrationForm
from user.models import User


# Home Page
@login_required
def home(request):
    return render(request, "registration/home.html")


# SignUp View
def signup_view(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password"])
            user.save()
            messages.success(request, "Account created successfully! Please log in.")
            return redirect("login")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = RegistrationForm()
    
    return render(request, "registration/signup.html", {"form": form})

# Login View 
def login_view(request):
    if request.method == "POST":
        email = request.POST.get('email')  
        password = request.POST.get('password')

        user = authenticate(request, username=email, password=password)  

        if user is not None:
            login(request, user)
            messages.success(request, "Login successful.")

            from chama.utils import get_user_dashboard_redirect
            dashboard_url = get_user_dashboard_redirect(user)
            return redirect(dashboard_url)

        else:
            messages.error(request, "Invalid email or password.")

    return render(request, "registration/login.html")

# Logout View
def logout_view(request):
    logout(request)
    return redirect('/')
