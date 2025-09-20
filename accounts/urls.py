
from django.urls import path,include
from rest_framework.routers import DefaultRouter
from .views import normal_register, verify_otp, logout_view 
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views

urlpatterns = [
    path('profile/', views.edit_profile, name='edit_profile'),
    path('login/', views.normal_login, name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'), 
    path('normal_register/', normal_register, name='register'),
    path('social_login_register/', views.social_login_register, name='social_login_register'),
    path('varify_otp/', verify_otp, name='verify_otp'),
    path('change_email_otp/', views.request_email_change_otp, name='change_email'),
    path('change_email_verify_otp/', views.change_email_verify_otp, name='forgor_password_otp'),  
    path('change_email/', views.change_email_final, name='change_email'),
    path('change_password/', views.change_password, name='change_password'),
    path('logout/', views.logout_view, name='logout'),
    path('resend_otp/', views.resend_otp, name='resend_otp'),
    path('forgot_password/', views.forget_password, name='forgor_password'),
    path('forgot_password_verify_otp/', views.on_change_verify_otp, name='forgor_password_otp'),   
    path('forgot_password_change/', views.forgot_password_change, name='forgor_password_change'),   
]
