from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views


router = DefaultRouter()
router.register(r'departments', views.DepartmentViewSet, basename='department')
router.register(r'teams', views.TeamViewSet, basename='team')
router.register(r'projects', views.ProjectViewSet, basename='project')
router.register(r'define-columns', views.DefineColumnsViewSet, basename='define-column')


urlpatterns = [
    path('', include(router.urls)),
    path('columns/<int:pk>/', views.get_columns, name='get-columns'),
    path('happy-path/<int:pk>/', views.happy_path, name='ideal-path'),
    path('happy-path/', views.happy_path, name='ideal-path-create'),
    path('ideal-path/<int:pk>/', views.get_ideal_paths, name='get-ideal-paths'),
    path('cycle-time/<int:pk>/', views.get_cycle_time, name='get-ideal-paths'),
    path('average-vs-median-by-month/<int:pk>/', views.average_vs_median_by_month, name='get-average-vs-median'),
    path('total-case-count/<int:pk>/', views.total_case_count, name='total-case-count'),
    path('total-idle-time-&-ratio/<int:pk>/', views.total_idle_time, name='total-idle-time'),
    path('total-loops-&-ratio/<int:pk>/', views.loops_and_ratio, name='loops_and_ratio'),
    path('total-bottleneck-&-ratio/<int:pk>/', views.bottleneck_and_ratio, name='bottlenec_and_ratio'),
    path('calculate-step-and-cases/<int:pk>/', views.cal_step_and_cases, name='setep_and_cases'),
    path('dropout-rate/<int:pk>/', views.dropout_rate, name='dropout_rate'),
    path('average-activity-time/<int:pk>/', views.average_activity_time, name='average_activity_time'),
    path('process-variants/<int:pk>/', views.process_variants, name='process_variants'),
]
