from django.contrib import admin
from .models import HappyPath, kpiList, Visualization
# Register your models here.
admin.site.register(HappyPath)

admin.site.register(kpiList)
admin.site.register(Visualization)