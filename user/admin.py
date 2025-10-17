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
    User_password1 = forms.CharField(
        label = "Password",
        widget = forms.PasswordInput,
        min_length = 8#use min_length
    )
    User_password2 = forms.CharField(
        label = "Confirm Password",
        widget = forms.PasswordInput
    )

    class Meta:
        model = User
        fields = ("User_username","User_first_name","User_last_name","User_email",
                  "User_is_email_verified","User_national_id","User_status",
                  "User_phone_number")
        
    def clean_password2(self):
        User_password1 = self.cleaned_data.get("User_password1")
        User_password2 = self.cleaned_data.get("User_password2")
        if User_password1 and User_password2 and User_password1 != User_password2:
            raise ValidationError("Passwords do not match")
        return User_password2
    
    def save(self, commit= True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["User_password1"])  # Hash the password
        if commit:
            user.save()
        return user

#Get Custom UserAdmin
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    fieldsets = UserAdmin.fieldsets
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("User_username","User_first_name","User_last_name","User_email",
                  "User_is_email_verified","User_national_id","User_status",
                  "User_phone_number","User_password1","User_password2"),
        }),
    )

admin.site.register(User, CustomUserAdmin)