from rest_framework import serializers
from .models import Department, Team, Project, DefineColumns, HappyPath, kpiList, Visualization, kpiDashboard
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
        fields = ['id', 'user', 'process', 'department', 'team', 'department_id', 'team_id', 'csv_file', 'status', 'related_project', 'is_related', 'created_at', 'updated_at']
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


class VisualizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visualization
        fields = ['name']


class KpiListSerializer(serializers.ModelSerializer):   
    visualizations = serializers.SerializerMethodField()

    class Meta:
        model = kpiList
        fields = [
            "id", "kpi_name", "visualizations"
        ]

    def get_visualizations(self, obj):       
        return list(obj.visualizations.all().values_list('type', flat=True))
    


class KpiDashboardSerializer(serializers.ModelSerializer):      
    
    class Meta:
        model = kpiDashboard       
        fields = [
            'id',             
            'user',               
            'project',                
            'name', 
            'data'
        ]       
        read_only_fields = ['user'] 