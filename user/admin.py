from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django import forms
from django.core.exceptions import ValidationError

# Get Custom user model
User = get_user_model()


# Custom User Creation Form
class CustomUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        min_length=8  # minimum length validation
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput
    )

    class Meta:
        model = User
        fields = (
            "user_first_name",
            "user_last_name",
            "user_email",
            "user_is_email_verified",
            "user_national_id",
            "user_status",
            "user_phone_number",
        )

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords do not match")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])  # Hash the password
        if commit:
            user.save()
        return user


# Custom User Admin
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    model = User

    list_display = (
        "user_email",
        "user_first_name",
        "user_last_name",
        "user_phone_number",
        "user_status",
        "is_staff",
        "is_active",
    )
    list_filter = ("user_status", "is_staff", "is_active")
    ordering = ("user_email",)
    search_fields = (
        "user_email",
        "user_first_name",
        "user_last_name",
        "user_phone_number",
    )

    fieldsets = (
        (None, {"fields": ("user_email", "password")}),
        ("Personal Info", {"fields": (
            "user_first_name",
            "user_last_name",
            "user_national_id",
            "user_phone_number",
            "user_profile_picture",
        )}),
        ("Permissions", {"fields": (
            "is_staff",
            "is_active",
            "is_superuser",
            "groups",
            "user_permissions",
        )}),
        ("Status & Dates", {"fields": (
            "user_status",
            "user_date_joined",
            "user_is_email_verified",
        )}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "user_email",
                "user_first_name",
                "user_last_name",
                "user_national_id",
                "user_phone_number",
                "password1",
                "password2",
                "is_staff",
                "is_active",
            ),
        }),
    )


admin.site.register(User, CustomUserAdmin)