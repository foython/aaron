from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import TotalCompanies, Testimonial, FAQ
from .serializers import TotalCompaniesSerializer, TestimonialSerializer, FAQSerializer
from .ai import get_chatbot_response
from datetime import datetime
from rest_framework import status
import json


@api_view(['GET'])
@permission_classes([AllowAny])
def company_list(request):    
    companies = TotalCompanies.objects.all()      
    serializer = TotalCompaniesSerializer(companies, many=True)     
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def testimonial_list(request):    
    testimonials = Testimonial.objects.all()
    serializer = TestimonialSerializer(testimonials, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def faq_list(request):    
    faqs = FAQ.objects.all()
    serializer = FAQSerializer(faqs, many=True)
    return Response(serializer.data)


@api_view(['POST'])
def chatbot_for_website(request):
    conversation_history = request.data.get('previous_conversation', None) 
    message = request.data.get('message')
    
    if not message:
        return Response({"error": "Message is required"}, status=status.HTTP_400_BAD_REQUEST)    
   
    bot_response = get_chatbot_response(
        message, 
        # prev_context=conversation_history # Renamed argument to match function def
    )    
    return Response(
        {
            bot_response
        },
        status=200
    )
