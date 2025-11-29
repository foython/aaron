from django.db import models
from accounts.models import TimeStamp



class TotalCompanies(TimeStamp):
    total = models.IntegerField()  
    
    def __str__(self):
        return str(self.total)

class Companies_logo(TimeStamp):
    company = models.ForeignKey(TotalCompanies, on_delete=models.CASCADE)
    logo = models.ImageField(upload_to='company_logo/')



class Testimonial(TimeStamp):
    name = models.CharField(max_length=64, blank=True, null=True)
    designation = models.CharField(max_length=64, blank=True, null=True)    
    profile_picture = models.ImageField(upload_to='testimonial_profile/', blank=True, null=True)
    testimonial = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name
    

class FAQ(TimeStamp):
    question = models.CharField(max_length=256, blank=True, null=True)
    answer = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.question
    