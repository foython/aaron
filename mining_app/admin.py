from django.contrib import admin
from .models import HappyPath, kpiList, Visualization, ProcessVariant, DefineColumns, Team, Department, Project, CostPerProcess
# Register your models here.
admin.site.register(HappyPath)
admin.site.register(Project)
admin.site.register(kpiList)
admin.site.register(Visualization)
admin.site.register(ProcessVariant)
admin.site.register(DefineColumns)
admin.site.register(CostPerProcess)