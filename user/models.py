from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator


class CustomUserManager(BaseUserManager):
    def create_user(self, user_email, password=None, **extra_fields):
        """Create and save a regular user."""
        if not user_email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(user_email)
        user = self.model(user_email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, user_email, password=None, **extra_fields):
        """Create and save a superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(user_email, password, **extra_fields)


class User(AbstractUser):
    username = None  # Disable Django's default username field

    user_phone_regex = RegexValidator(
        regex=r'^\+\d{1,3}\d{9}$',
        message="Phone number must start with '+' followed by country code and 9 digits."
    )

    user_phone_number = models.CharField(
        max_length=13,
        validators=[user_phone_regex]
    )
    user_first_name = models.CharField(max_length=30)
    user_last_name = models.CharField(max_length=30)
    user_email = models.EmailField(max_length=50, unique=True)
    user_is_email_verified = models.BooleanField(default=False)
    user_national_id = models.CharField(max_length=8, unique=True)
    user_profile_picture = models.ImageField(
        upload_to='profile_pics/',
        default='profile_pics/default.png',
        blank=True,
        null=True
    )
    user_status = models.CharField(
        max_length=8,
        choices=[
            ('active', 'Active'),
            ('inactive', 'Inactive')
        ],
        default='active'
    )
    user_date_joined = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "user_email"
    REQUIRED_FIELDS = [
        "user_first_name",
        "user_last_name",
        "user_national_id",
        "user_phone_number"
    ]

    def __str__(self):
        return f"{self.user_first_name} {self.user_last_name}"
