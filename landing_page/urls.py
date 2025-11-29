
from django.urls import path,include
from . import views

urlpatterns = [
    path('company_logo/', views.company_list, name='edit_profile'),    
    path('testimonial/', views.testimonial_list, name='testimonial'),
    path('faq/', views.faq_list, name='faq'),
    path('chatbot/', views.chatbot_for_website, name='chatbot_for_website'),
     
]
