from django.contrib import admin
from user.models import User
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django import forms
from django.core.exceptions import ValidationError
# Register your models here.

#Get Custom user model
User = get_user_model()

#Custom User Creation Form
class CustomUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(
        label = "Password",
        widget = forms.PasswordInput,
        min_length = 8#use min_length
    )
    password2 = forms.CharField(
        label = "Confirm Password",
        widget = forms.PasswordInput
    )

    class Meta:
        model = User
        fields = ("User_first_name","User_last_name","User_email",
                  "User_is_email_verified","User_national_id","User_status",
                  "User_phone_number")
        
    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords do not match")
        return password2
    
    def save(self, commit= True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])  # Hash the password
        if commit:
            user.save()
        return user

#Get Custom UserAdmin
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    model = User

    list_display = (
        "User_email",
        "User_first_name",
        "User_last_name",
        "User_phone_number",
        "User_status",
        "is_staff",
        "is_active",
    )
    list_filter = ("User_status", "is_staff", "is_active")
    ordering = ("User_email",)
    search_fields = (
        "User_email",
        "User_first_name",
        "User_last_name",
        "User_phone_number",
    )

    fieldsets = (
        (None, {"fields": ("User_email", "password")}),
        ("Personal Info", {"fields": (
            "User_first_name",
            "User_last_name",
            "User_national_id",
            "User_phone_number",
            "User_profile_picture",
        )}),
        ("Permissions", {"fields": (
            "is_staff",
            "is_active",
            "is_superuser",
            "groups",
            "user_permissions",
        )}),
        ("Status & Dates", {"fields": (
            "User_status",
            "User_date_joined",
            "User_is_email_verified",
        )}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "User_email",
                "User_first_name",
                "User_last_name",
                "User_national_id",
                "User_phone_number",
                "password1",
                "password2",
                "is_staff",
                "is_active",
            ),
        }),
    )


admin.site.register(User, CustomUserAdmin)