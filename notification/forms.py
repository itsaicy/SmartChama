from django import forms
from notification.models import Meeting, Notification, UserNotificationSettings

class UserNotificationSettingsForm(forms.ModelForm):
    class Meta:
        model = UserNotificationSettings
        fields = [
            'user_notification_settings_allow_email',
            'user_notification_settings_allow_sms',
            'user_notification_settings_allow_inapp',
            'user_notification_settings_fallback',
        ]
        widgets = {
            'user_notification_settings_allow_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'user_notification_settings_allow_sms': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'user_notification_settings_allow_inapp': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'user_notification_settings_fallback': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class NotificationForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = [
            'notification_title',
            'notification_message',
            'notification_type',
            'notification_priority',
        ]
        widgets = {
            'notification_title': forms.TextInput(attrs={
                'class': 'form-control bg-transparent text-white',
                'placeholder': 'Meeting Reminder'
            }),
            'notification_message': forms.Textarea(attrs={
                'class': 'form-control bg-transparent text-white',
                'rows': 6,
                'placeholder': 'Enter your notification message here...'
            }),
            'notification_type': forms.Select(attrs={
                'class': 'form-select form-select-sm bg-transparent text-white',
                'style': 'min-width:160px;'
            }),
            'notification_priority': forms.Select(attrs={
                'class': 'form-select form-select-sm bg-transparent text-white',
                'style': 'min-width:120px;'
            }),
        }



class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = [
            'meeting_title',
            'meeting_date',
            'meeting_type',
            'meeting_venue',
            'meeting_online_link',
            'meeting_agenda',
        ]
        widgets = {
            'meeting_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Monthly Contribution Review',
                'id': 'meeting_title'
            }),
            'meeting_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
                'id': 'meeting_date'
            }),
            'meeting_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'meeting_type'
            }),
            'meeting_venue': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter meeting address',
                'id': 'meeting_venue'
            }),
            'meeting_online_link': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'Paste online meeting link',
                'id': 'meeting_online_link'
            }),
            'meeting_agenda': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter meeting agenda details...',
                'id': 'meeting_agenda'
            }),
        }
