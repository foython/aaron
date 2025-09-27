from django.shortcuts import render
from rest_framework import viewsets, permissions
from django.contrib.auth.models import User
from .models import Department, Team, Project, DefineColumns
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import pandas as pd
from .serializers import (
    DepartmentSerializer,
    TeamSerializer,
    ProjectSerializer,
    DefineColumnsSerializer
)


class DepartmentViewSet(viewsets.ModelViewSet):
   
    queryset = Department.objects.all().order_by('-created_at')
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
    
   
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TeamViewSet(viewsets.ModelViewSet):  
    queryset = Team.objects.all().order_by('-created_at')
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)



class ProjectViewSet(viewsets.ModelViewSet):
  
    queryset = Project.objects.all().order_by('-created_at')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

   
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)



class DefineColumnsViewSet(viewsets.ModelViewSet):
  
    queryset = DefineColumns.objects.all().order_by('-created_at')
    serializer_class = DefineColumnsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(project__user=self.request.user)
    

    def perform_create(self, serializer):
        
        define_columns_instance = serializer.save()        
        
        project = define_columns_instance.project
        project.status = True  
        project.save()


@api_view(['GET'])
def get_columns(request, pk=None):
    try:
        project = Project.objects.get(id=pk)
        
        df = pd.read_csv(project.csv_file.path, encoding='utf-8-sig')
        # df = pd.read_csv(project.csv_file.path, encoding='latin-1') 
        columns = df.columns.tolist()
        return Response({"columns": columns})
    except Project.DoesNotExist:
        return Response({"error": "No project found for this user."}, status=404)
    except FileNotFoundError:
        return Response({"error": "The specified CSV file could not be found."}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    

    
# @api_view(['GET', 'POST', 'PATCH', 'DELETE'])
# @permission_classes([IsAuthenticated])
# def project_view(request):

#     return render(request, 'mining_app/project.html')


