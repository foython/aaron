from rest_framework import serializers
from .models import Department, Team, Project, DefineColumns, HappyPath
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
    department = DepartmentSerializer(read_only=True)
    team = TeamSerializer(read_only=True)
    
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), source='department', write_only=True
    )    
   
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(), source='team', write_only=True
    )

    class Meta:
        model = Project        
        fields = ['id', 'user', 'process', 'department', 'team', 'department_id', 'team_id', 'csv_file', 'status', 'created_at', 'updated_at']
        read_only_fields = ['user', 'created_at', 'updated_at']
        


class DefineColumnsSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())

    class Meta:
        model = DefineColumns
        fields = ['id', 'project', 'happy_path', 'case_id', 'activity', 'timestamp_start', 'timestamp_end', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class HappyPathSerializer(serializers.ModelSerializer):
    class Meta:
        model = HappyPath
        fields = '__all__'