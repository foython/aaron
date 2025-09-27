from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import TotalCompanies, Testimonial, FAQ
from .serializers import TotalCompaniesSerializer, TestimonialSerializer, FAQSerializer

@api_view(['GET'])
def company_list(request):    
    companies = TotalCompanies.objects.all()      
    serializer = TotalCompaniesSerializer(companies, many=True)     
    return Response(serializer.data)


@api_view(['GET'])
def testimonial_list(request):    
    testimonials = Testimonial.objects.all()
    serializer = TestimonialSerializer(testimonials, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def faq_list(request):    
    faqs = FAQ.objects.all()
    serializer = FAQSerializer(faqs, many=True)
    return Response(serializer.data)
    