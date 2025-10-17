from django.shortcuts import render, redirect
from user.models import User
from django.contrib.auth import authenticate,login,logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from user.forms import RegistrationForm

#Home page
@login_required
def home(request):
    return render(request,"registration/home.html")

#SignUp View
def signup_view(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["User_password"])
            user.save()
            messages.success(request, "Account created successfully! Please log in.")
            return redirect("login")
        
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = RegistrationForm()
    
    return render(request, "registration/signup.html", {"form": form})

#Login View
def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, "Login successful.")
            return redirect("home") 
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, "registration/login.html")

#Logout View
def logout_view(request):
    logout(request)  
    return redirect('/')