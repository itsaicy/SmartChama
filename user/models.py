from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator

# Create your models here.
class User(AbstractUser):
    User_username = models.CharField(max_length=30, unique=True)
    User_phone_regex = RegexValidator(
        regex = r'^\+\d{1,3}\d{9}$',
        message = "Phone number must start with '+' followed by country code and 9 digits."
    )

    User_phone_number = models.CharField(
        max_length=13,
        validators=[User_phone_regex]
    )
    User_first_name = models.CharField(max_length=30)
    User_last_name = models.CharField(max_length=30)
    User_email = models.EmailField(max_length=50, unique=True)
    User_is_email_verified =models.BooleanField(default=False)
    User_national_id = models.CharField(max_length=8, unique=True)
    User_profile_picture = models.ImageField(
        upload_to='profile_pics/', 
        default='profile_pics/default.png',
        blank=True,
        null=True)
    User_status = models.CharField(
        max_length=8,
        choices=[('active', 'Active'), ('inactive', 'Inactive')],
        default='active'
    )
    User_date_joined = models.DateTimeField(auto_now_add=True)

    
    USERNAME_FIELD = "User_username"  
    REQUIRED_FIELDS = ["User_first_name",
                       "User_last_name",
                       "User_national_id",
                       "User_phone_number"]
    
    def __str__(self):
        return f"{self.User_first_name} {self.User_last_name}"

