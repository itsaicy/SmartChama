from django import forms
from chama.models import Chama

class ChamaForm(forms.ModelForm):
    class Meta:
        model = Chama
        fields = [
            'chama_name',
            'chama_description',
            'chama_contribution_amount',
            'chama_contribution_frequency',
            'chama_custom_frequency_days',
            'chama_max_members',
            'chama_rota_type',
        ]
        widgets = {
            'chama_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter Chama name'
            }),
            'chama_description': forms.Textarea(attrs={
                'class': 'form-control', 
                'placeholder': 'Briefly describe your Chama',
                'rows': 3
            }),
            'chama_contribution_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Ksh.5000'
            }),
            'chama_contribution_frequency': forms.Select(attrs={
                'class': 'form-select'
            }),
            'chama_custom_frequency_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Only if frequency is custom'
            }),
            'chama_max_members': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 10'
            }),
            'chama_rota_type': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
