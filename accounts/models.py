from django.db import models
from django.db import models
from django.contrib.auth.models import AbstractUser
import random
import string


# Create your models here.
class TimeStamp(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        

class CustomUser(AbstractUser, TimeStamp):  
    first_name = models.CharField(max_length=64, blank=True, null=True)
    last_name = models.CharField(max_length=64, blank=True, null=True)    
    gender = models.CharField(max_length=28, blank=True, null=True)
    profession = models.CharField(max_length=64, blank=True, null=True)
    company_name = models.CharField(max_length=256, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile/', blank=True, null=True)
    phone_number = models.CharField(max_length=28, blank=True, null=True)
    location = models.CharField(max_length=28, blank=True, null=True)
    country = models.CharField(max_length=28, blank=True, null=True)
    time_zone = models.CharField(max_length=8, blank=True, null=True)
    upload_logo = models.ImageField(upload_to='logo/', blank=True, null=True)
    about_yourself = models.TextField(blank=True, null=True)
    professional_background = models.TextField(blank=True, null=True)
    auth_provider = models.CharField(max_length=20, default="normal")
    is_varified = models.BooleanField(default=False)
    otp = models.CharField(max_length=6, blank=True, null=True) 
    processes = models.IntegerField(default=0)
    chatbot_inquiries = models.IntegerField(default=0)
    is_subscribed = models.BooleanField(default=False)
    subsciption_expires_on = models.DateTimeField(blank=True, null=True)
    subscription_status = models.CharField(max_length=100, blank=True,)
    subscription_id = models.CharField(max_length=100, blank=True, null=True)
    
    

    def generate_otp(self):
        otp = ''.join(random.choices(string.digits, k=4))
        self.otp = otp
        self.save()
        return otp
    
    
    def __str__(self):
        return f"{self.id} {self.username}"