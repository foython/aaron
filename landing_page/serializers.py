from rest_framework import serializers
from .models import TotalCompanies, Companies_logo, Testimonial, FAQ

class CompanyLogoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Companies_logo
        fields = ('logo',)
        

class TotalCompaniesSerializer(serializers.ModelSerializer):
    company_logo = CompanyLogoSerializer(many=True, read_only=True, source='companies_logo_set')
    
    class Meta:
        model = TotalCompanies
        fields = ('id', 'total', 'company_logo')




class TestimonialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Testimonial
        fields = ['name', 'designation', 'profile_picture', 'testimonial']

class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ['question', 'answer']
