
from rest_framework import serializers
from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

User = get_user_model()


class CustomUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    age = serializers.SerializerMethodField(read_only=True)  # <-- add this

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'username', 'email', 'password', 'gender', 'profession', 'company_name',
            'date_of_birth', 'age', 'profile_picture', 'phone_number', 'location', 'country',
            'time_zone', 'upload_logo', 'about_yourself', 'professional_background', 'created_at', 'is_subscribed', 'subsciption_plan_name', 'subsciption_expires_on',
            'subscription_status'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'username': {'required': True},
        }

    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)

    def get_age(self, obj):        
        if not obj.date_of_birth:
            return None
        today = date.today()
        return today.year - obj.date_of_birth.year - (
            (today.month, today.day) < (obj.date_of_birth.month, obj.date_of_birth.day)
        )



class OTPVerifySerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)
