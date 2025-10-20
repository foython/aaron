from django.shortcuts import render
from rest_framework import viewsets, permissions
from django.contrib.auth.models import User
from .models import Department, Team, Project, DefineColumns, HappyPath, kpiList, kpiDashboard
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import pandas as pd
from .serializers import (
    DepartmentSerializer,
    TeamSerializer,
    ProjectSerializer,
    DefineColumnsSerializer,
    HappyPathSerializer,
    KpiListSerializer,
    KpiDashboardSerializer

)
from .utils import *
import pandas as pd
from rest_framework.decorators import api_view
from rest_framework.response import Response
import json



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
    

    
@api_view(['GET', 'POST', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def project_api_view(request, pk=None):
    
    if request.method == 'GET':
        if pk is not None:
            # DETAIL VIEW: Retrieve a single project
            try:
                # Retrieve the project, ensuring it belongs to the requesting user
                project = Project.objects.get(pk=pk, user=request.user)
                serializer = ProjectSerializer(project)
                return Response(serializer.data)
            except Project.DoesNotExist:
                return Response(
                    {"detail": "Project not found or you do not have permission to view it."},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # LIST VIEW: Retrieve all projects for the authenticated user
            projects = Project.objects.filter(user=request.user).order_by('-created_at')
            serializer = ProjectSerializer(projects, many=True)
            return Response(serializer.data)

    # --- CREATE (POST) ---
    elif request.method == 'POST':
       
        data = request.data        
        related_project_id = data.get('related_project')

        if related_project_id:
            related_data = data.pop('related_project', None) # <--- This line is problematic if 'related_project' is defined on the serializer
            serializer = ProjectSerializer(data=request.data)   
            if serializer.is_valid():              
                new_project = serializer.save(user=request.user, is_related=True) # Save the new project
                
                # Update the parent project's 'related_project' field
                try:
                    parent_project = Project.objects.get(
                        pk=related_project_id,
                        user=request.user
                    ) 
                    
                    parent_project.related_project = new_project
                    parent_project.save()
                   
                    
                    return Response(serializer.data, status=status.HTTP_201_CREATED) # <--- ADDED RETURN HERE
                    
                except Project.DoesNotExist:
                    # Handle case where the specified related_project doesn't exist for the user
                    return Response(
                        {"related_project": "The specified related project was not found or does not belong to you."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) # <--- ADDED RETURN HERE
        
        # ... (existing code for when related_project_id is NOT present)
        else:
            serializer = ProjectSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(user=request.user)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            # You should also add a return for invalid data here
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) # <--- ADDED RETURN HERE

    
    # --- UPDATE (PATCH) ---
    elif request.method == 'PATCH':
        if pk is None:
            return Response(
                {"detail": "Method not allowed. PATCH requires a primary key (pk)."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED
            )

        try:
            # Retrieve the project, ensuring it belongs to the requesting user
            project = Project.objects.get(pk=pk, user=request.user)
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found or you do not have permission to edit it."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Use partial=True for PATCH to allow only a subset of fields
        serializer = ProjectSerializer(
            project,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            # Note: The user field is read_only, so attempting to change it will be ignored by DRF.
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # --- DELETE ---
    elif request.method == 'DELETE':
        if pk is None:
            return Response(
                {"detail": "Method not allowed. DELETE requires a primary key (pk)."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED
            )

        try:
            # Retrieve the project, ensuring it belongs to the requesting user
            project = Project.objects.get(pk=pk, user=request.user)
            project.delete()
            return Response(
                {"detail": "Project deleted successfully."},
                status=status.HTTP_204_NO_CONTENT
            )
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found or you do not have permission to delete it."},
                status=status.HTTP_404_NOT_FOUND
            )

    return Response(
        {"detail": "Method not allowed."},
        status=status.HTTP_405_METHOD_NOT_ALLOWED
    )




@api_view(['GET', 'POST'])
def happy_path(request, pk=None):   
    
    if request.method == 'GET':
        try:
            project = Project.objects.get(id=pk)
            ideal_paths = project.happypath_set.all().order_by('serial_number')
            
            # Serialize the data
            serializer = HappyPathSerializer(ideal_paths, many=True)
            
            return Response({
                "project_id": project.id,                
                "happy_paths": serializer.data
            })
        except Project.DoesNotExist:
            return Response({"error": "No project found with this ID."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)
    
    elif request.method == 'POST':
        try:
            serializer = HappyPathSerializer(data=request.data)
            
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
        



@api_view(['GET'])
def get_cycle_time(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)
       
        event_log_data = df_log.to_dict('records')
        
        result_json_string = calculate_all_cycle_time_metrics_from_model(
                event_log_data,
                columns.case_id,
                columns.timestamp_start,
                columns.timestamp_end, # Ensure this is the correct column name for completion time
                office_start_hour=6, # Assuming you have these fields on Project model
                office_end_hour=18,     # Assuming you have these fields on Project model
                time_unit='hours'
            )
        
        result_data = json.loads(result_json_string)
        
        return Response({
            "cycle_time_data": result_data
        })
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
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
    file_path = project.csv_file.path
    df_log = pd.read_csv(file_path)
    
    PROJECT_START_HOUR = 6
    PROJECT_END_HOUR = 18 

    print(f"--- Running Monthly Cycle Time Calculation on {file_path} with {PROJECT_START_HOUR}:00-{PROJECT_END_HOUR}:00 Business Hours ---")
    
    try:
        df_log = pd.read_csv(file_path)

        required_cols = [CASE_ID_COL, START_TIME_COL, COMPLETE_TIME_COL]
        if not all(col in df_log.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_log.columns]
            return Response({
            json.dumps({"Error": f"Required columns missing: {missing}"}, indent=4)
        })
            
        else:       
            data_to_pass = df_log.to_dict('records')
        
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
    
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        case_count_json_string = calculate_total_cases(event_log_data, columns.case_id)

        result_data = json.loads(case_count_json_string)

        return Response(result_data) 
        
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    




@api_view(['GET'])
def total_idle_time(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

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
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def loops_and_ratio(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

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
        return Response({"error": str(e)}, status=500)



@api_view(['GET'])
def bottleneck_and_ratio(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_bottleneck_metrics(event_log_data=event_log_data,
                case_id_col=columns.case_id,
                activity_col=columns.activity,
                start_time_col=columns.timestamp_start,
                complete_time_col=columns.timestamp_end
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def cal_step_and_cases(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_steps_per_case_metrics(event_log_data, columns.case_id)
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:  
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def dropout_rate(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

      
        result = calculate_dropout_rate(event_log_data, columns.case_id, columns.activity, columns.timestamp_end)
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def average_activity_time(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_average_activity_duration(event_log_data, columns.activity,columns.timestamp_start, columns.timestamp_end)
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def process_variants(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

  
        result = calculate_process_variants(event_log_data, columns.case_id, columns.activity, columns.timestamp_end)
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)





@api_view(['GET'])
def top_variants(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_top_variants(
            event_log_data,
            columns.case_id,
            columns.activity,
            columns.timestamp_end,
            top_n=5 
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)



@api_view(['GET'])
def first_pass_rate(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_first_pass_rate(
            event_log_data,
            columns.case_id,
            columns.activity
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:

        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def longest_waiting_time(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_longest_waiting_time_step(
            event_log_data,
            columns.case_id,
            columns.activity,
            columns.timestamp_start,
            columns.timestamp_end
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:

        return Response({"error": str(e)}, status=500)



@api_view(['GET'])
def variant_complexity_index(request, pk=None):
    try:
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_variant_complexity_index(
            event_log_data,
            columns.case_id,
            columns.activity,
            columns.timestamp_end
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)



@api_view(['GET'])
def variant_change_over_time(request, pk=None):
    try:
        time_param = request.query_params.get('time', None)
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_variant_change_over_time(
            event_log_data,
            columns.case_id,
            columns.activity,
            columns.timestamp_end,
            time_period=time_param.upper() # 'D' for Daily, 'W' for Weekly, 'M' for Monthly
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    

    
@api_view(['GET'])
def cases_following_top_variant(request, pk=None):
    try:
        
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')


        result = calculate_cases_following_top_variant(
            event_log_data,
            columns.case_id,
            columns.activity,
            columns.timestamp_end
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def max_steps_in_a_case(request, pk=None):
    try:
        
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_max_steps_in_a_case(event_log_data, columns.case_id)
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def activity_frequency_distribution(request, pk=None):
    try:
        
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_activity_frequency_distribution(event_log_data, columns.activity)
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def time_saved_potential(request, pk=None):
    try:
        
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_time_saved_potential(
            event_log_data, 
            columns.case_id, 
            columns.timestamp_start, 
            columns.timestamp_end
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    

@api_view(['GET'])
def happy_path_compliance(request, pk=None):
    try:
        
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        happy_path = project.happypath_set.all().order_by('serial_number')
        serializer = HappyPathSerializer(happy_path, many=True)      
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_happy_path_compliance(
            event_log_data, 
            columns.case_id, 
            columns.activity, 
            columns.timestamp_start, 
            serializer.data
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:      
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def total_completed_cases(request, pk=None):
    try:
        
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)


        event_log_data = df_log.to_dict('records')

        result = calculate_total_completed_cases(event_log_data, columns.case_id)
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:        
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def happy_path_deviation(request, pk=None):
    try:
        
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        happy_path = project.happypath_set.all().order_by('serial_number')
        serializer = HappyPathSerializer(happy_path, many=True)         
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

        result = calculate_happy_path_deviation(
            event_log_data, 
            columns.case_id, 
            columns.activity, 
            columns.timestamp_start,
            columns.timestamp_end, 
            serializer.data
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:        
        return Response({"error": str(e)}, status=500)




@api_view(['GET'])
def skipped_steps_rate(request, pk=None):
    try:
        
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        happy_path = project.happypath_set.all().order_by('serial_number')
        serializer = HappyPathSerializer(happy_path, many=True)         
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

       
        result = calculate_skipped_steps_rate(
            event_log_data, 
            columns.case_id, 
            columns.activity, 
            serializer.data
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:        
        return Response({"error": str(e)}, status=500)
    



@api_view(['GET'])
def case_throughput_rate(request, pk=None):
    try:
        time_param = request.query_params.get('time', None)
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)           
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)
  
        event_log_data = df_log.to_dict('records')
 
        result = calculate_case_throughput_rate(
            event_log_data, 
            columns.case_id, 
            columns.timestamp_end,
            period=time_param.upper() # 'D' for Day, 'W' for Week, 'M' for Month
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:       
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def kpi_list_view(request):
    try:
        kpis = kpiList.objects.all()
        serializer = KpiListSerializer(kpis, many=True)
        return Response(serializer.data)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
    
@api_view(['GET', 'POST', 'PATCH', 'DELETE']) # <-- Updated to include PATCH and DELETE
def kpi_dashboard(request, project_id=None, pk=None): 
        
    if not request.user.is_authenticated:
        return Response(
            {"detail": "Authentication credentials were not provided or recognized."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if request.method == 'GET':        
        dashboards = kpiDashboard.objects.filter(user=request.user)

        if project_id:           
            dashboards = dashboards.filter(project_id=project_id)        
              
        dashboards = dashboards.select_related('user', 'project')
        
        serializer = KpiDashboardSerializer(dashboards, many=True)
        return Response(serializer.data)


    elif request.method == 'POST':
        data = request.data.copy()
        
        
        if project_id and 'project' not in data:
            data['project'] = project_id 
            
        serializer = KpiDashboardSerializer(data=data)
        
        if serializer.is_valid():           
            serializer.save(user=request.user) 
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    elif request.method == 'PATCH':
        if pk is None:
            return Response(
                {"detail": "Method not allowed. PATCH requires a dashboard ID (pk)."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED
            )

        try:
            instance = kpiDashboard.objects.get(pk=pk, user=request.user)
        except kpiDashboard.DoesNotExist:
            return Response(
                {"detail": "Dashboard not found or access denied."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = KpiDashboardSerializer(instance, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    elif request.method == 'DELETE':
        if pk is None:
            return Response(
                {"detail": "Method not allowed. DELETE requires a dashboard ID (pk)."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED
            )
      
        try:
            instance = kpiDashboard.objects.get(pk=pk, user=request.user)
        except kpiDashboard.DoesNotExist:
            return Response(
                {"detail": "Dashboard not found or access denied."},
                status=status.HTTP_404_NOT_FOUND
            )

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    return Response(
        {"detail": "Method not allowed."},
        status=status.HTTP_405_METHOD_NOT_ALLOWED
    )

# @api_view(['GET', 'POST'])
# def kpi_dashboard(request, project_id=None):     
#     if request.method == 'GET':        
#         if request.user.is_authenticated:            
#             dashboards = kpiDashboard.objects.filter(user=request.user)

#             if project_id:              
#                 dashboards = dashboards.filter(project_id=project_id)            
            
#             dashboards = dashboards.select_related('user', 'project')
            
#             serializer = KpiDashboardSerializer(dashboards, many=True)
#             return Response(serializer.data)
#         else:
#             return Response(
#                 {"detail": "Authentication credentials were not provided or recognized."},
#                 status=status.HTTP_401_UNAUTHORIZED
#             )


#     elif request.method == 'POST':
        
#         serializer = KpiDashboardSerializer(data=request.data)
        
#         if serializer.is_valid():
            
#             if request.user.is_authenticated:                
#                 serializer.save(user=request.user) 
#                 return Response(serializer.data, status=status.HTTP_201_CREATED)
#             else:
#                 return Response(
#                     {"detail": "Authentication credentials were not provided or recognized."},
#                     status=status.HTTP_401_UNAUTHORIZED
#                 )

#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    



@api_view(['POST'])
def simlation_run(request):
    try:
        user = request.user
        data = request.data
        return Response(data, status=status.HTTP_201_CREATED)        
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def actual_path_data_with_connections(request, pk=None):
    try:
        time_param = request.query_params.get('time', None)
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)           
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)
  
        event_log_data = df_log.to_dict('records')
 
        result = analyze_and_structure_process_data(
            event_log_data, 
            columns.case_id, 
            columns.activity,
            columns.timestamp_start,
            columns.timestamp_end
            
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:       
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def actual_path_data_with(request, pk=None):
    try:
        time_param = request.query_params.get('time', None)
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)           
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)
  
        event_log_data = df_log.to_dict('records')
 
        result = analyze_and_structure_process_datas(
            event_log_data, 
            columns.case_id, 
            columns.activity,
            columns.timestamp_start,
            columns.timestamp_end
            
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:       
        return Response({"error": str(e)}, status=500)
    

@api_view(['GET'])
def actual_path_data_with_problems(request, pk=None):
    try:
        time_param = request.query_params.get('time', None)
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)           
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)
  
        event_log_data = df_log.to_dict('records')
 
        result = analyze_path_kpi_benchmarks(
            event_log_data, 
            columns.case_id, 
            columns.activity,
            columns.timestamp_start,
            columns.timestamp_end
            
        )
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:       
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def banchmarking_view(request):   
    projects = Project.objects.filter(user=request.user)
    
    serializer = ProjectSerializer(projects, many=True)
    serialized_data = serializer.data
    
    filtered_and_shaped_data = []
    
    for project_data in serialized_data:
        
        if project_data.get('is_related') == False:
            
            shaped_project = {
                'id': project_data.get('id'),
                'process': project_data.get('process'),
                'date': project_data.get('created_at'), # Assuming 'created_at' is the desired date
                'csv_file': project_data.get('csv_file'),
                'related_project': project_data.get('related_project'),
            }
            filtered_and_shaped_data.append(shaped_project)
   
    return Response(filtered_and_shaped_data, status=status.HTTP_200_OK)


@api_view(['GET'])
def banchmark_report(request, pk=None):
    try:
        
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        project = Project.objects.get(pk=pk)
        compair = Project.objects.get(pk=project.related_project__id)


        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')

       
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:        
        return Response({"error": str(e)}, status=500)


