from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from user.forms import RegistrationForm, UserProfileForm
from user.models import User
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import EmailMessage
from user.tokens import account_activation_token
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import get_user_model
from chama.models import Membership

# Utility: prevent duplicate messages
def add_message_once(request, level, text):
    existing = [msg.message for msg in messages.get_messages(request)]
    if text not in existing:
        messages.add_message(request, level, text)

@login_required
def home(request):
    """Landing page shown only to new users with no chama memberships."""
    user = request.user

    has_membership = Membership.objects.filter(
        membership_user=user,
        membership_status="active"
    ).exists()

    if has_membership:
    
        return redirect("chama:my_chamas")  
    else:
        # Show landing page for new users
        return render(request, "registration/home.html")

# Email Confirmation
def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = get_user_model().objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.save()
        add_message_once(request, messages.SUCCESS, "Thank you for your email confirmation. Now you can log in.")
        return redirect("login")
    else:
        add_message_once(request, messages.SUCCESS, "Activation link is invalid or expired.")
        return redirect("login")  # redirect to login instead of home

def activateEmail(request, user, to_email):
    mail_subject = "Activate your SmartChama account"
    message = render_to_string("registration/account_activation.html", {
        "user": user,
        "domain": get_current_site(request).domain,
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": account_activation_token.make_token(user),
        "protocol": "https" if request.is_secure() else "http",
    })
    email = EmailMessage(mail_subject, message, to=[to_email])
    email.content_subtype = "html"
    if email.send():
        add_message_once(request, messages.SUCCESS,
            f"Dear {user.user_first_name}, please check your email ({to_email}) for an activation link. "
            "Note: Check your spam folder if you do not see it.")
    else:
        add_message_once(request, messages.SUCCESS,
            f"Problem sending email to {to_email}. Please verify the address.")

# SignUp View
def signup_view(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.set_password(form.cleaned_data["password"])
            user.save()
            activateEmail(request, user, form.cleaned_data.get("user_email"))

            add_message_once(request, messages.SUCCESS,
                "Account created successfully! Please check your email to confirm your account before logging in.")
            return redirect("login")  
        else:
            for error in list(form.errors.values()):
                add_message_once(request, messages.SUCCESS, error)
    else:
        form = RegistrationForm()

    return render(request, "registration/signup.html", {"form": form})

from chama.models import Membership

def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            add_message_once(request, messages.SUCCESS, "Login successful.")

            # Check for active chama memberships
            membership = (
                Membership.objects
                .filter(membership_user=user, membership_status="active")
                .select_related("membership_chama")
                .first()
            )

            if membership:
                chama_id = membership.membership_chama.id
                role = membership.membership_role.lower()

                # Redirect based on role
                if role == "admin":
                    return redirect("dashboard:admin_dashboard", chama_id=chama_id)
                elif role == "treasurer":
                    return redirect("dashboard:treasurer_dashboard", chama_id=chama_id)
                elif role == "secretary":
                    return redirect("dashboard:secretary_dashboard", chama_id=chama_id)
                else:
                    return redirect("dashboard:member_dashboard", chama_id=chama_id)

            
            return redirect("home")
        else:
            add_message_once(request, messages.SUCCESS, "Invalid email or password.")

    return render(request, "registration/login.html")



# Logout View
def logout_view(request):
    logout(request)
    return redirect("/")

# Profile Edit
@login_required
def edit_profile(request):
    user = request.user
    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            add_message_once(request, messages.SUCCESS, "Profile updated successfully!")
            return redirect("profile")
        else:
            add_message_once(request, messages.SUCCESS, "Please correct the error below.")
    else:
        form = UserProfileForm(instance=user)

    return render(request, "settings/edit_profile.html", {"form": form})

@login_required
def upload_profile_picture(request):
    if request.method == "POST":
        if "user_profile_picture" in request.FILES:
            user = request.user
            user.user_profile_picture = request.FILES["user_profile_picture"]
            user.save()
            add_message_once(request, messages.SUCCESS, "Profile picture updated successfully!")
        elif "profile_image" in request.FILES:
            user = request.user
            user.user_profile_picture = request.FILES["profile_image"]
            user.save()
            add_message_once(request, messages.SUCCESS, "Profile picture updated successfully!")
        else:
            add_message_once(request, messages.SUCCESS, "No image selected.")

    return redirect(request.META.get("HTTP_REFERER", "/"))

@login_required
def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            add_message_once(request, messages.SUCCESS, "Your password was successfully updated!")
            return redirect("profile")
        else:
            add_message_once(request, messages.SUCCESS, "Please correct the error below.")
    else:
        form = PasswordChangeForm(request.user)

    return render(request, "registration/password_change.html", {"form": form})
