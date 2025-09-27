from rest_framework import serializers
from .models import Department, Team, Project, DefineColumns

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'user', 'name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['user', 'created_at', 'updated_at']

class TeamSerializer(serializers.ModelSerializer):
   
    class Meta:
        model = Team
        fields = ['id', 'user', 'name', 'description', 'created_at', 'updated_at']
        read_only_fields = ['user', 'created_at', 'updated_at']
    

class ProjectSerializer(serializers.ModelSerializer):
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all())
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all())

    class Meta:
        model = Project
        fields = ['id', 'user', 'process', 'department', 'team', 'csv_file', 'status', 'created_at', 'updated_at']
        read_only_fields = ['user', 'created_at', 'updated_at']

        

class DefineColumnsSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())

    class Meta:
        model = DefineColumns
        fields = ['id', 'project', 'happy_path', 'case_id', 'activity', 'timestamp_start', 'timestamp_end', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']