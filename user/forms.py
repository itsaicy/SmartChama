from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'placeholder': 'Password',
        'class': 'form-control'
    }))

    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={
        'placeholder': 'Confirm Password',
        'class': 'form-control'
    }))

    class Meta:
        model = User
        fields = [
            "user_first_name",
            "user_last_name",
            "user_email",
            "user_national_id",
            "user_phone_number"
        ]

        widgets = {
            'user_first_name': forms.TextInput(attrs={
                'placeholder': 'First Name',
                'class': 'form-control'
            }),
            'user_last_name': forms.TextInput(attrs={
                'placeholder': 'Last Name',
                'class': 'form-control'
            }),
            'user_email': forms.EmailInput(attrs={
                'placeholder': 'Email Address',
                'class': 'form-control'
            }),
            'user_phone_number': forms.TextInput(attrs={
                'placeholder': 'Phone Number',
                'class': 'form-control'
            }),
            'user_national_id': forms.TextInput(attrs={
                'placeholder': 'National ID',
                'class': 'form-control'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user