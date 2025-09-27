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
]
