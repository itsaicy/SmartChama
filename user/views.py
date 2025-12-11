from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from user.forms import RegistrationForm, UserProfileForm
from user.models import User
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_encode,urlsafe_base64_decode
from django.utils.encoding import force_bytes,force_str
from django.core.mail import EmailMessage
from user.tokens import account_activation_token
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm

# Home Page
@login_required
def home(request):
    return render(request, "registration/home.html")

#Email Confirmation
from django.contrib.auth import get_user_model

def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = get_user_model().objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, 'Thank you for your email confirmation.\
                          Now you can login your account')
        
        
        return redirect('login')
    else:
        messages.error(request, "Activation link is invalid")
    return redirect('signup')

def activateEmail(request, user, to_email):
    mail_subject = 'Activate your user account'
    message = render_to_string("registration/account_activation.html", {
        'user':user.user_first_name,
        'domain': get_current_site(request).domain,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': account_activation_token.make_token(user),
        'protocol': 'https' if request.is_secure() else 'http'
    })
    email = EmailMessage(mail_subject, message, to=[to_email])
    if email.send():
         messages.success(request, 
             f"Dear {user}, please check your email ({to_email}) for an activation link to complete your registration. " 
              "Note: Check your spam folder if you do not see it.")
    else:
        messages.error(request, f'Problem sending email to {to_email}, check if you typed it corectly.')

# SignUp View
def signup_view(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.set_password(form.cleaned_data["password"])
            user.save()
            activateEmail(request, user, form.cleaned_data.get('user_email'))

            messages.success(request, "Account created successfully! Please log in.")
            return redirect("login")
        
        else:
            for error in list(form.errors.values()):
               messages.error(request, error)
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

#Profile Edit
@login_required
def edit_profile(request):
    user = request.user
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('profile') 
    else:
        form = UserProfileForm(instance=user)

    return render(request, 'settings/edit_profile.html', {'form': form})

@login_required
def upload_profile_picture(request):
    if request.method == 'POST':
        # Check if file is provided in the request
        if 'user_profile_picture' in request.FILES:
            user = request.user
            user.user_profile_picture = request.FILES['user_profile_picture']
            user.save()
            messages.success(request, "Profile picture updated successfully!")
        elif 'profile_image' in request.FILES: 
            # Handle case where input name might be different in dashboard HTML
            user = request.user
            user.user_profile_picture = request.FILES['profile_image']
            user.save()
            messages.success(request, "Profile picture updated successfully!")
        else:
            messages.error(request, "No image selected.")

    # Redirect back to the page the user came from (The Dashboard)
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # This is critical: it keeps the user logged in after password change
            update_session_auth_hash(request, user) 
            messages.success(request, 'Your password was successfully updated!')
            return redirect('profile') # Redirects back to the profile page
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'registration/password_change.html', {
        'form': form
    })