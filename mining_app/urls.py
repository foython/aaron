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
    path('top-variants/<int:pk>/', views.top_variants, name='top_variants'),
    path('first-pass-rate/<int:pk>/', views.first_pass_rate, name='first_pass_rate'),
    path('longest-waiting-time/<int:pk>/', views.longest_waiting_time, name='longest_waiting_time'),
    path('variant-complexity-index/<int:pk>/', views.variant_complexity_index, name='variant_complexity_index'),
    path('variant-change-over-time/<int:pk>/', views.variant_change_over_time, name='variant_change_over_time'),
    path('cases-following-top-variant/<int:pk>/', views.cases_following_top_variant, name='cases_following_top_variant'),
    path('max-steps-in-a-case/<int:pk>/', views.max_steps_in_a_case, name='max_steps_in_a_case'),
    path('time-saved-potential/<int:pk>/', views.time_saved_potential, name='time_saved_potential'),
    path('activity-frequency-distribution/<int:pk>/', views.activity_frequency_distribution, name='activity_frequency_distribution'),
]
