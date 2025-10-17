from django import forms
from user.models import User
from django.contrib.auth import get_user_model

User = get_user_model()

class RegistrationForm(forms.ModelForm):
    User_password = forms.CharField(widget=forms.PasswordInput(attrs={
        'placeholder': 'Password',
        'class': 'form-control'
    }))

    User_confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={
        'placeholder': 'Confirm Password',
        'class': 'form-control'
    }))

    class Meta:
        model = User
        fields = ["User_username","User_first_name","User_last_name","User_email"
                  ,"User_national_id","User_phone_number"]
        widgets = {
            'User_username': forms.TextInput(attrs={
                'placeholder': 'Username',
                'class': 'form-control'
            }),
            'User_first_name': forms.TextInput(attrs={
                'placeholder': 'FirstName',
                'class': 'form-control'
            }),
            'User_last_name': forms.TextInput(attrs={
                'placeholder': 'LastName',
                'class': 'form-control'
            }),
            'User_email': forms.EmailInput(attrs={
                'placeholder': 'Email',
                'class': 'form-control'
            }),
            'User_phone_number': forms.TextInput(attrs={
                'placeholder': 'Phone Number',
                'class': 'form-control'
            }),
            'User_national_id': forms.NumberInput(attrs={
                'placeholder': 'National ID',
                'class': 'form-control'
            }),

        }

        
        def clean(self):
            cleaned_data = super().clean()
            User_password = cleaned_data.get("User_password")
            User_confirm_password = cleaned_data.get("User_confirm_password")
            if User_password and User_confirm_password and User_password != User_confirm_password:
                raise forms.ValidationError("Passwords do not match.")
            return cleaned_data
        