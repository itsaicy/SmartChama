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

class ChamaPaymentForm(forms.ModelForm):
    class Meta:
        model = Chama
        fields = [
            'chama_payment_method',
            'chama_paybill_number',
            'chama_paybill_name',
            'chama_paybill_account_number',
            'chama_till_number',
            'chama_till_name',
        ]
        widgets = {
            'chama_payment_method': forms.Select(attrs={'class': 'form-select'}),
            'chama_paybill_number': forms.TextInput(attrs={'class': 'form-control'}),
            'chama_paybill_name': forms.TextInput(attrs={'class': 'form-control'}),
            'chama_paybill_account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'chama_till_number': forms.TextInput(attrs={'class': 'form-control'}),
            'chama_till_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        chama_payment_method = cleaned_data.get("chama_payment_method")
        paybill_number = cleaned_data.get("chama_paybill_number")
        till_number = cleaned_data.get("chama_till_number")

        # If Paybill is selected
        if chama_payment_method == "paybill":
            if not paybill_number:
                raise forms.ValidationError("Paybill number is required.")
            if till_number:
                raise forms.ValidationError("You cannot fill Till fields when Paybill is selected.")

        # If Till is selected
        if chama_payment_method == "till":
            if not till_number:
                raise forms.ValidationError("Till number is required.")
            if paybill_number:
                raise forms.ValidationError("You cannot fill Paybill fields when Till is selected.")

        return cleaned_data
