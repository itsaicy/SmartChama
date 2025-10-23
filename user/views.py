from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from user.forms import RegistrationForm
from user.models import User


# Home Page
@login_required
def home(request):
    return render(request, "registration/home.html")


# Sign Up View
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


# Login View (now uses email instead of username)
def login_view(request):
    if request.method == "POST":
        email = request.POST.get('email')  # changed from 'username' → 'email'
        password = request.POST.get('password')

        user = authenticate(request, email=email, password=password)  # updated

        if user is not None:
            login(request, user)
            messages.success(request, "Login successful.")
            return redirect("home")
        else:
            messages.error(request, "Invalid email or password.")

    return render(request, "registration/login.html")


# Logout View
def logout_view(request):
    logout(request)
    return redirect('/')
