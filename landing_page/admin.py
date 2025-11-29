from django.contrib import admin
from .models import TotalCompanies, Companies_logo, Testimonial, FAQ


class CompaniesLogoInline(admin.StackedInline):
    model = Companies_logo
   
class TotalCompaniesAdmin(admin.ModelAdmin):
   
    inlines = [CompaniesLogoInline]


admin.site.register(TotalCompanies, TotalCompaniesAdmin)

admin.site.register(Companies_logo)


admin.site.register(Testimonial)
admin.site.register(FAQ)