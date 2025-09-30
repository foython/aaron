from django.shortcuts import render
from rest_framework import viewsets, permissions
from django.contrib.auth.models import User
from .models import Department, Team, Project, DefineColumns, IdealPath

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import pandas as pd
from .serializers import (
    DepartmentSerializer,
    TeamSerializer,
    ProjectSerializer,
    DefineColumnsSerializer,
    IdealPathSerializer,
)
from .utils import *


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



@api_view(['GET', 'POST'])
def happy_path(request, pk=None):   
    
    if request.method == 'GET':
        try:
            project = Project.objects.get(id=pk)
            ideal_paths = project.idealpath_set.all().order_by('serial_number')
            
            # Serialize the data
            serializer = IdealPathSerializer(ideal_paths, many=True)
            
            return Response({
                "project_id": project.id,
                "project_name": project.name,  # Assuming Project model has a 'name' field
                "ideal_paths": serializer.data
            })
        except Project.DoesNotExist:
            return Response({"error": "No project found with this ID."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)
    
    elif request.method == 'POST':
        try:
            # Use serializer to validate and save data
            serializer = IdealPathSerializer(data=request.data)
            
            if serializer.is_valid():
                ideal_path = serializer.save()
                return Response({
                    "message": "Ideal path added successfully.",
                    "ideal_path_id": ideal_path.id,
                    "data": serializer.data
                }, status=201)
            else:
                return Response({
                    "error": "Invalid data",
                    "details": serializer.errors
                }, status=400)
                
        except Project.DoesNotExist:
            return Response({"error": "No project found with the provided ID."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)
        
import json
        
@api_view(['GET'])
def get_ideal_paths(request, pk=None):
    try:
        project = Project.objects.get(id=pk)
        ideal_path_json = analyze_standard_path_performance_json(file_path=project.csv_file.path)
        ideal_path_data = json.loads(ideal_path_json)  # Parse the JSON string        
        
        return Response({
            "ideal_path": ideal_path_data
        })
    except Project.DoesNotExist:
        return Response({"error": "No project found with this ID."}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    

    
import pandas as pd
from rest_framework.decorators import api_view
from rest_framework.response import Response
import json
# Assuming Project and DefineColumns models are imported
# from .models import Project, DefineColumns 

# --- (Your calculate_net_working_time and calculate_all_cycle_time_metrics_from_model functions go here) ---


@api_view(['GET'])
def get_cycle_time(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        
        # 1. Load the CSV file from the path
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # 2. Extract the required data as a list of dictionaries (records)
        # This structure is what calculate_all_cycle_time_metrics_from_model expects.
        event_log_data = df_log.to_dict('records')

        # 3. Call the metric calculation function
        # NOTE: columns.timestamp_end is likely meant to be columns.timestamp_complete
        result_json_string = calculate_all_cycle_time_metrics_from_model(
                event_log_data,
                columns.case_id,
                columns.timestamp_start,
                columns.timestamp_end, # Ensure this is the correct column name for completion time
                office_start_hour=6, # Assuming you have these fields on Project model
                office_end_hour=18,     # Assuming you have these fields on Project model
                time_unit='hours'
            )
        
        # The result is already a JSON string from the calculation function, 
        # so we need to parse it back into a Python dict before putting it in the final Response.
        result_data = json.loads(result_json_string)
        
        return Response({
            "cycle_time_data": result_data
        })
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        # Return a clean error message
        return Response({"error": str(e)}, status=500)
    


    
@api_view(['GET'])
def average_vs_median_by_month(request, pk=None):
    project = Project.objects.get(pk=pk) 
    if project.user != request.user:
        return Response({"error": "You do not have permission to access this project."}, status=403)
        
    columns = DefineColumns.objects.get(project=project)
    CASE_ID_COL = columns.case_id
    START_TIME_COL = columns.timestamp_start
    COMPLETE_TIME_COL = columns.timestamp_end  # Ensure this is the correct column name for completion   
        # 1. Load the CSV file from the path
    file_path = project.csv_file.path
    df_log = pd.read_csv(file_path)
    
    PROJECT_START_HOUR = 6
    PROJECT_END_HOUR = 18 

    print(f"--- Running Monthly Cycle Time Calculation on {file_path} with {PROJECT_START_HOUR}:00-{PROJECT_END_HOUR}:00 Business Hours ---")
    
    try:
        # Load the CSV file locally
        df_log = pd.read_csv(file_path)
        
        # Check if required columns exist before proceeding
        required_cols = [CASE_ID_COL, START_TIME_COL, COMPLETE_TIME_COL]
        if not all(col in df_log.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_log.columns]
            return Response({
            json.dumps({"Error": f"Required columns missing: {missing}"}, indent=4)
        })
            
        else:
            # Convert the DataFrame to a list of dictionaries (records)
            data_to_pass = df_log.to_dict('records')

            # Call the main function
            results_json = create_monthly_cycle_time_data(
                event_log_data=data_to_pass,
                case_id_col=CASE_ID_COL,
                start_time_col=START_TIME_COL,
                complete_time_col=COMPLETE_TIME_COL,
                office_start_hour=PROJECT_START_HOUR,
                office_end_hour=PROJECT_END_HOUR
            )
            
            result_data = json.loads(results_json)
        
        return Response({
            "cycle_time_data": result_data
        })
    except FileNotFoundError:
        print(json.dumps({"Error": f"File not found: {file_path}. Please ensure it is in the same directory."}, indent=4))
    except Exception as e:
        print(json.dumps({"Error": f"A critical error occurred during local file processing: {e}"}, indent=4))


@api_view(['GET'])
def total_case_count(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        
        # 1. Load the CSV file from the path
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # 2. Extract the required data as a list of dictionaries (records)
        event_log_data = df_log.to_dict('records')

        # 3. Calculate the total cases (returns a JSON string)
        case_count_json_string = calculate_total_cases(event_log_data, columns.case_id)
        
        # 4. Parse the JSON string into a Python dictionary
        result_data = json.loads(case_count_json_string)
        
        # 5. FIX: Pass the dictionary directly to the Response object.
        # This prevents Python from attempting to create an unhashable set.
        return Response(result_data) 
        
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        # Return a clean error message
        return Response({"error": str(e)}, status=500)
    




@api_view(['GET'])
def total_idle_time(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        
        # 1. Load the CSV file from the path
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # 2. Extract the required data as a list of dictionaries (records)
        event_log_data = df_log.to_dict('records')

        # 3. Calculate the total cases (returns a JSON string)
        idle_time = calculate_total_idle_time_metrics(event_log_data=event_log_data,
                case_id_col=columns.case_id,
                start_time_col=columns.timestamp_start,
                complete_time_col=columns.timestamp_end,
                office_start_hour=6,
                office_end_hour=18)
        result_data = json.loads(idle_time)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        # Return a clean error message
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def loops_and_ratio(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        
        # 1. Load the CSV file from the path
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # 2. Extract the required data as a list of dictionaries (records)
        event_log_data = df_log.to_dict('records')

        # 3. Calculate the total cases (returns a JSON string)
        total_loops_ratio = calculate_loop_metrics(event_log_data=event_log_data,
                case_id_col=columns.case_id,
                activity_col=columns.activity
        )
        result_data = json.loads(total_loops_ratio)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        # Return a clean error message
        return Response({"error": str(e)}, status=500)



@api_view(['GET'])
def bottleneck_and_ratio(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        
        # 1. Load the CSV file from the path
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # 2. Extract the required data as a list of dictionaries (records)
        event_log_data = df_log.to_dict('records')

        # 3. Calculate the total cases (returns a JSON string)
        total_loops_ratio = calculate_bottleneck_metrics(event_log_data=event_log_data,
                case_id_col=columns.case_id,
                activity_col=columns.activity,
                start_time_col=columns.timestamp_start,
                complete_time_col=columns.timestamp_end
        )
        result_data = json.loads(total_loops_ratio)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        # Return a clean error message
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def cal_step_and_cases(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        
        # 1. Load the CSV file from the path
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # 2. Extract the required data as a list of dictionaries (records)
        event_log_data = df_log.to_dict('records')

        # 3. Calculate the total cases (returns a JSON string)
        total_loops_ratio = calculate_steps_per_case_metrics(event_log_data, columns.case_id)
        result_data = json.loads(total_loops_ratio)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        # Return a clean error message
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def dropout_rate(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        
        # 1. Load the CSV file from the path
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # 2. Extract the required data as a list of dictionaries (records)
        event_log_data = df_log.to_dict('records')

        # 3. Calculate the total cases (returns a JSON string)
        total_loops_ratio = calculate_dropout_rate(event_log_data, columns.case_id, columns.activity, columns.timestamp_end)
        result_data = json.loads(total_loops_ratio)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        # Return a clean error message
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def average_activity_time(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        
        # 1. Load the CSV file from the path
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # 2. Extract the required data as a list of dictionaries (records)
        event_log_data = df_log.to_dict('records')

        # 3. Calculate the total cases (returns a JSON string)
        total_loops_ratio = calculate_average_activity_duration(event_log_data, columns.activity,columns.timestamp_start, columns.timestamp_end)
        result_data = json.loads(total_loops_ratio)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        # Return a clean error message
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def process_variants(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        
        # 1. Load the CSV file from the path
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # 2. Extract the required data as a list of dictionaries (records)
        event_log_data = df_log.to_dict('records')

        # 3. Calculate the total cases (returns a JSON string)
        total_loops_ratio = calculate_process_variants(event_log_data, columns.case_id, columns.activity, columns.timestamp_end)
        result_data = json.loads(total_loops_ratio)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        # Return a clean error message
        return Response({"error": str(e)}, status=500)

