# admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('username', 'email', 'auth_provider', 'is_active', 'is_staff')
    list_filter = ('auth_provider', 'is_active', 'is_staff')

    fieldsets = (
        (None, {'fields': ('username', 'email', 'auth_provider', 'password', 'is_varified')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'gender', 'profession', 'company_name', 'date_of_birth', 'profile_picture', 'phone_number', 'location', 'country', 'time_zone', 'upload_logo', 'about_yourself', 'professional_background')}),
        ('Subscription', {'fields': ('is_subscribed','subsciption_plan_name', 'subsciption_expires_on', 'subscription_status', 'subscription_id')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.auth_provider != "normal":
            return self.readonly_fields + ('password',)
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        if obj.auth_provider != "normal" and not obj.password.startswith('pbkdf2_'):
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)
