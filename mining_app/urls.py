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
    path('project-view/', views.project_api_view, name='project_view'),
    path('project-view/<int:pk>/', views.project_api_view, name='project_view'),
    path('columns/<int:pk>/', views.get_columns, name='get-columns'),
    path('process-variants/<int:pk>/', views.get_process_variants_view, name='get-process-variants'),    
    path('happy-path/<int:pk>/', views.happy_path, name='ideal-path'),
    path('happy-path/', views.happy_path, name='ideal-path-create'),
    path('cost-per-process/', views.cost_per_process_list_create, name='cost_per_process_list_create'),
    path('cost-per-process/<int:pk>/', views.cost_per_process_list_create, name='cost_per_process_list_create'),
    path('ideal-path/<int:pk>/', views.get_ideal_paths, name='get-ideal-paths'),
    path('cycle-time/<int:pk>/', views.filtered_cycle_time, name='filtered_cycle_time'),
    path('average-vs-median-by-time/<int:pk>/', views.time_series_cycle_time_metrics, name='get-average-vs-median'),
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
    path('happy-path-compliance/<int:pk>/', views.happy_path_compliance, name='happy_path_compliance'),
    path('total-completed-cases/<int:pk>/', views.total_completed_cases, name='total_completed_cases'),
    path('happy-path-deviation/<int:pk>/', views.happy_path_deviation, name='happy_path_deviation'),
    path('skipped-steps-rate/<int:pk>/', views.skipped_steps_rate, name='skipped_steps_rate'),
    path('case-throughput-rate/<int:pk>/', views.case_throughput_rate, name='case_throughput_rate'),
    path('actual-path-data-with-connections/<int:pk>/', views.actual_path_data_with, name='actual_path_data_with_connections'),
    path('kpi-list/', views.kpi_list_view, name='kpi_list_view'),
    path('dashboard/<int:project_id>/<int:pk>/', views.kpi_dashboard, name='kpi_dashboard'),
    path('dashboard/<int:project_id>/', views.kpi_dashboard, name='kpi_dashboard_by_project_id'),     
    path('dashboard/', views.kpi_dashboard, name='save_dashboard'),
    path('actual-path-data-problems/<int:pk>/', views.actual_path_data_with_problems, name='actual_path_data_with_connections'),
    path('banchmarking-view/', views.banchmarking_view, name='banchmarking_view'),
    path('cycle-filter/<int:pk>/', views.time_series_cycle_time_metrics, name='cycle_filter'),
    path('kpi-summary-metrics/<int:pk>/', views.kpi_summary_metrics, name='kpi_summary_metrics'),
    path('export-benchmark-pdf/', views.export_kpi_benchmark_pdf, name='export_kpi_benchmark_pdf'),
    path('process-variants/<int:pk>/', views.process_variants, name='process_variants'),
    path('cost-per-process/<int:pk>/', views.cost_per_process_view, name='cost_per_case'),    
    path('average-deviation-view/<int:pk>/', views.average_deviation_view, name='average_deviation'),
    path('happy-path-compliance-rate/<int:pk>/', views.happy_path_compliance_view, name='happy_path_compliance_rate'),
    path('simulation/', views.simulate_actual_path_view, name='simulate_process_view'),
    path('simulation/<int:pk>/', views.simulate_process_view, name='simulate_process_view'),
]


