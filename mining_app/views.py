from django.shortcuts import render
from rest_framework import viewsets, permissions
from django.contrib.auth.models import User
from .models import Department, Team, Project, DefineColumns, HappyPath, kpiList, kpiDashboard, ProcessVariant, CostPerProcess
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
    KpiDashboardSerializer,
    ProcessVariantSerializer,
    CostPerProcessSerializer

)
from .utils import *
import pandas as pd
from rest_framework.decorators import api_view
from rest_framework.response import Response
import json
from .fil import *
import re 
import os
# from .filter import filter_event_log_pre_kpi


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
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        data = calculate_variants_and_metrics(
            df_log.to_dict(orient="records"),
            define_columns_instance.case_id,
            define_columns_instance.activity,
            define_columns_instance.timestamp_start
        )

        
        save_process_variants(project, data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_process_variants_view(request, pk):
    """
    GET endpoint to retrieve all saved process variants for a specific project.
    No recalculation is done.
    """
    try:
        # 1️⃣ Ensure project belongs to current user
        project = Project.objects.get(pk=pk, user=request.user)

        # 2️⃣ Fetch related process variants
        variants = ProcessVariant.objects.filter(project=project).order_by('-case_count')

        # 3️⃣ Serialize and return
        serializer = ProcessVariantSerializer(variants, many=True)

        return Response({
            "project_id": project.id,
            "total_variants": len(serializer.data),
            "variants": serializer.data
        }, status=status.HTTP_200_OK)

    except Project.DoesNotExist:
        return Response(
            {"error": "Project not found or not owned by user."},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {"error": f"An unexpected error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


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
    

def normalize_timestamps(file_path, save_clean_copy=False):
    
    df = pd.read_csv(file_path)

    
    timestamp_cols = [
        col for col in df.columns if 'time' in col.lower() or 'date' in col.lower()
    ]

    for col in timestamp_cols:
        df[col] = (
            pd.to_datetime(df[col], errors='coerce')
            .dt.tz_localize(None)
            .dt.strftime('%Y-%m-%d %H:%M:%S')
        )

    if save_clean_copy:
        new_path = file_path.replace(".csv", "_cleaned.csv")
        df.to_csv(new_path, index=False)
        return new_path
    else:
        df.to_csv(file_path, index=False)
        return file_path


# === Main View ===
@api_view(['GET', 'POST', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def project_api_view(request, pk=None):
    
    # --- GET (List or Detail) ---
    if request.method == 'GET':
        if pk is not None:
            try:
                project = Project.objects.get(pk=pk, user=request.user)
                serializer = ProjectSerializer(project)
                return Response(serializer.data)
            except Project.DoesNotExist:
                return Response(
                    {"detail": "Project not found or you do not have permission to view it."},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            projects = Project.objects.filter(user=request.user).order_by('-created_at')
            serializer = ProjectSerializer(projects, many=True)
            return Response(serializer.data)

    # --- POST (Create) ---
    elif request.method == 'POST':
        data = request.data        
        related_project_id = data.get('related_project')
        user = request.user

        # --- ✅ Check subscription status ---
        # if not user.subscription_active:
        #     return Response(
        #         {"detail": "Your subscription has expired or is inactive. Please renew to upload new processes."},
        #         status=status.HTTP_403_FORBIDDEN
        #     )

        # --- ✅ Check upload limit ---
        user_project_count = Project.objects.filter(user=user).count()
        if user_project_count >= user.plan_upload_limit:
            return Response(
                {"detail": f"Upload limit reached. Your plan ({user.subsciption_plan_name}) allows only {user.plan_upload_limit} processes."},
                status=status.HTTP_403_FORBIDDEN
            )

        # --- Continue with your existing logic ---
        serializer = ProjectSerializer(data=request.data)
        if serializer.is_valid():
            new_project = serializer.save(user=user, is_related=bool(related_project_id))

            # Normalize timestamps
            try:
                if new_project.csv_file and os.path.exists(new_project.csv_file.path):
                    normalize_timestamps(new_project.csv_file.path)
            except Exception as e:
                print(f"⚠️ Timestamp normalization failed: {e}")

            # Handle related project linking
            if related_project_id:
                try:
                    parent_project = Project.objects.get(pk=related_project_id, user=user)
                    parent_project.related_project = new_project
                    parent_project.save()
                except Project.DoesNotExist:
                    return Response(
                        {"related_project": "The specified related project was not found or does not belong to you."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # --- PATCH (Update) ---
    elif request.method == 'PATCH':
        if pk is None:
            return Response(
                {"detail": "PATCH requires a project ID (pk)."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED
            )
        project = get_object_or_404(Project, pk=pk, user=request.user)
        serializer = ProjectSerializer(project, data=request.data, partial=True)
        if serializer.is_valid():
            updated_project = serializer.save()
            
            # Auto-normalize if CSV file updated
            if 'csv_file' in request.data:
                try:
                    normalize_timestamps(updated_project.csv_file.path)
                except Exception as e:
                    print(f"⚠️ Timestamp normalization failed during update: {e}")
            
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # --- DELETE ---
    elif request.method == 'DELETE':
        if pk is None:
            return Response(
                {"detail": "DELETE requires a project ID (pk)."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED
            )
        project = get_object_or_404(Project, pk=pk, user=request.user)
        project.delete()
        return Response({"detail": "Project deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

    return Response({"detail": "Method not allowed."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)




@api_view(['GET', 'PATCH'])
def happy_path(request, pk=None):   
    try:
        project = Project.objects.get(id=pk)
    except Project.DoesNotExist:
        return Response({"error": "No project found with this ID."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------------
    # 🔹 GET: Fetch all HappyPath records
    # -------------------------
    if request.method == 'GET':
        try:
            happy_paths = project.happypath_set.all().order_by('serial_number')
            serializer = HappyPathSerializer(happy_paths, many=True)
            
            return Response({
                "project_id": project.id,
                "happy_paths": serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # -------------------------
    # 🔹 PATCH: Update existing HappyPath record
    # -------------------------
    elif request.method == 'PATCH':
        try:
            record_id = request.data.get("id")
            if not record_id:
                return Response({"error": "Missing 'id' field for update."}, status=status.HTTP_400_BAD_REQUEST)

            # Find the record
            try:
                happy_path_obj = HappyPath.objects.get(id=record_id, project=project)
            except HappyPath.DoesNotExist:
                return Response({"error": f"No HappyPath found with ID {record_id} for this project."}, status=status.HTTP_404_NOT_FOUND)

            # --- Load actual durations from event log ---
            try:
                columns = DefineColumns.objects.get(project=project)
                df = pd.read_csv(project.csv_file.path)

                df[columns.timestamp_start] = pd.to_datetime(df[columns.timestamp_start], errors='coerce')
                df[columns.timestamp_end] = pd.to_datetime(df[columns.timestamp_end], errors='coerce')
                df["duration_min"] = (df[columns.timestamp_end] - df[columns.timestamp_start]).dt.total_seconds() / 60

                # Average duration per activity from actual log
                actual_avg_durations = df.groupby(columns.activity)["duration_min"].mean().to_dict()
            except Exception as e:
                actual_avg_durations = {}
                print(f"[WARN] Could not compute actual durations: {e}")

            # --- Extract info from request / model ---
            act_name = request.data.get("activity_name", happy_path_obj.activity_name)
            happy_avg_time = request.data.get("average_time_minutes", happy_path_obj.average_time_minutes)

            try:
                happy_avg_time = float(happy_avg_time)
            except (ValueError, TypeError):
                happy_avg_time = None

            actual_time = actual_avg_durations.get(act_name)
            description_text = ""

            # --- Compare times ---
            if actual_time and happy_avg_time is not None:
                diff = happy_avg_time - actual_time
                diff_percent = (diff / actual_time) * 100 if actual_time > 0 else 0

                if diff_percent > 0:
                    description_text = (
                        f"{act_name} takes {round(abs(diff_percent), 2)}% longer than actual average "
                        f"(+{round(abs(diff), 2)} min)."
                    )
                elif diff_percent < 0:
                    description_text = (
                        f"{act_name} is {round(abs(diff_percent), 2)}% faster than actual average "
                        f"(-{round(abs(diff), 2)} min)."
                    )
                else:
                    description_text = f"{act_name} matches the actual average duration exactly ({round(actual_time, 2)} min)."
            else:
                description_text = f"No actual duration found for {act_name} in event log."

            # --- Save the record with the description ---
            update_data = {**request.data, "description": description_text}

            serializer = HappyPathSerializer(happy_path_obj, data=update_data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({
                    "message": "Happy path record updated successfully.",
                    "description": description_text,
                    "data": serializer.data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "error": "Invalid data provided.",
                    "details": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

@api_view(['GET', 'POST'])
def cost_per_process_list_create(request, pk=None):
    """
    GET: Retrieve CostPerProcess records (filtered by user/project/pk)
    POST: Create or update CostPerProcess records
    """
    if request.method == 'GET':
        filters = {'project__user': request.user}
        if pk is not None:
            filters['project__id'] = pk

        costs = CostPerProcess.objects.filter(**filters)
        if not costs.exists():
            return Response(
                {"detail": "No cost per process data found matching the criteria."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = CostPerProcessSerializer(costs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        data = request.data
        if not isinstance(data, list):
            data = [data]

        updated_records = []

        for item in data:
            project_id = item.get('project')
            activity_name = item.get('activity_name')

            if not (project_id and activity_name):
                return Response(
                    {"detail": "Both 'project' and 'activity_name' are required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                existing = CostPerProcess.objects.get(
                    project__id=project_id,
                    activity_name=activity_name,
                    project__user=request.user
                )
                # Use serializer for partial update
                serializer = CostPerProcessSerializer(existing, data=item, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    updated_records.append(serializer.data)
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            except CostPerProcess.DoesNotExist:
                serializer = CostPerProcessSerializer(data=item)
                if serializer.is_valid():
                    serializer.save()
                    updated_records.append(serializer.data)
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(updated_records, status=status.HTTP_200_OK)

        
        
@api_view(['GET'])
def get_ideal_paths(request, pk=None):
    try:
        # 1️⃣ Get the project
        project = Project.objects.get(id=pk)

        # 2️⃣ Get the column definitions (user-defined mapping)
        try:
            columns = DefineColumns.objects.get(project=project)
        except DefineColumns.DoesNotExist:
            return Response(
                {"error": "DefineColumns not found for this project."},
                status=400
            )

        # 3️⃣ Generate the ideal path using dynamic columns
        ideal_path_json = analyze_standard_path_performance_json(
            file_path=project.csv_file.path,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            start_time_col=columns.timestamp_start,
            complete_time_col=columns.timestamp_end
        )

        ideal_path_data = json.loads(ideal_path_json)

        # 4️⃣ Clear any existing HappyPath records for this project
        HappyPath.objects.filter(project=project).delete()

        # 5️⃣ Save each step into HappyPath
        saved_records = []
        for idx, step in enumerate(ideal_path_data, start=1):
            happy_obj = HappyPath.objects.create(
                project=project,
                serial_number=int(step.get("serial_number", idx)),
                activity_name=step.get("activity_name", "Unknown Activity"),
                average_time_minutes=step.get("average_time_minutes", 0),
                cost=None  # Cost can be linked later if CostPerProcess exists
            )

            saved_records.append({
                "serial_number": happy_obj.serial_number,
                "activity_name": happy_obj.activity_name,
                "average_time_minutes": float(happy_obj.average_time_minutes),
                "cost": happy_obj.cost
            })

        # 6️⃣ Return success response
        return Response({
            "message": "Ideal path generated and saved successfully in HappyPath table.",
            "project_id": project.id,
            "ideal_path": ideal_path_data,
            "saved_steps": saved_records
        }, status=200)

    except Project.DoesNotExist:
        return Response(
            {"error": "No project found with this ID."},
            status=404
        )
    except ValueError as ve:
        # This captures missing or mismatched column errors from the analyzer
        return Response(
            {"error": f"Column mismatch: {str(ve)}"},
            status=400
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def average_cycle_time(request, pk=None):
    try:
        # --- 1. Extract Filters from Query Parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        
        # New: Get selected variant IDs (e.g., from a comma-separated string like '6,7,8')
        selected_variant_ids = request.query_params.getlist('variants')
        
        # Convert cycle time filters to float if they exist
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None

        # --- 2. Project and Permissions Check + Variant Path Lookup ---
        project = Project.objects.get(pk=pk) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        # Look up column definitions and data file
        columns = DefineColumns.objects.get(project=project)           
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # ⭐️ New Logic: Convert Variant IDs to Variant Paths ⭐️
        
        selected_variant_paths = None
        if selected_variant_ids: # Check if the list is not empty
            # Convert list of strings ['7', '6'] to list of integers [7, 6]
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            
            # Query the database for the corresponding variant_path strings
            variant_objects = ProcessVariant.objects.filter(
                id__in=variant_ids, # This correctly handles multiple IDs
                project=project
            )
            # Extract the actual variant_path strings
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            
            if not selected_variant_paths:
                # If IDs were requested but none were found/valid, pass an empty list
                selected_variant_paths = []
        
        # --- 3. Filter the Event Log ---
        # Pass the extracted parameters and the variant paths to the filtering function
        log_data = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # This is usually the column containing the variant path
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths, # 👈 Using the retrieved paths here
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # --- 4. Calculate KPIs on the Filtered Log ---
        event_log_data = log_data.to_dict('records')
        
        result = get_average_cycle_time_hours(
            event_log_data,
            columns.case_id,
            columns.timestamp_start,
            columns.timestamp_end,
            office_start_hour=6,
            office_end_hour=18,
            # time_unit='hours',
        )
        
        result_data = json.loads(result)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        return Response({"error": "Project matching query does not exist."}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown" 
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:       
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def median_cycle_time_view(request, pk=None):
    try:
        # --- 1. Extract Filters from Query Parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        
        # New: Get selected variant IDs (e.g., from a comma-separated string like '6,7,8')
        selected_variant_ids = request.query_params.getlist('variants')
        
        # Convert cycle time filters to float if they exist
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None

        # --- 2. Project and Permissions Check + Variant Path Lookup ---
        project = Project.objects.get(pk=pk) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        # Look up column definitions and data file
        columns = DefineColumns.objects.get(project=project)           
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # ⭐️ New Logic: Convert Variant IDs to Variant Paths ⭐️
        
        selected_variant_paths = None
        if selected_variant_ids: # Check if the list is not empty
            # Convert list of strings ['7', '6'] to list of integers [7, 6]
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            
            # Query the database for the corresponding variant_path strings
            variant_objects = ProcessVariant.objects.filter(
                id__in=variant_ids, # This correctly handles multiple IDs
                project=project
            )
            # Extract the actual variant_path strings
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            
            if not selected_variant_paths:
                # If IDs were requested but none were found/valid, pass an empty list
                selected_variant_paths = []
        
        # --- 3. Filter the Event Log ---
        # Pass the extracted parameters and the variant paths to the filtering function
        log_data = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # This is usually the column containing the variant path
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths, # 👈 Using the retrieved paths here
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # --- 4. Calculate KPIs on the Filtered Log ---
        event_log_data = log_data.to_dict('records')
        
        result = get_median_cycle_time_hours(
            event_log_data,
            columns.case_id,
            columns.timestamp_start,
            columns.timestamp_end,
            office_start_hour=6,
            office_end_hour=18,
            # time_unit='hours',
        )
        
        result_data = json.loads(result)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        return Response({"error": "Project matching query does not exist."}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown" 
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:       
        return Response({"error": str(e)}, status=500)




@api_view(['GET'])
def minimum_cycle_time_view(request, pk=None):
    try:
        # --- 1. Extract Filters from Query Parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        
        # New: Get selected variant IDs (e.g., from a comma-separated string like '6,7,8')
        selected_variant_ids = request.query_params.getlist('variants')
        
        # Convert cycle time filters to float if they exist
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None

        # --- 2. Project and Permissions Check + Variant Path Lookup ---
        project = Project.objects.get(pk=pk) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        # Look up column definitions and data file
        columns = DefineColumns.objects.get(project=project)           
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # ⭐️ New Logic: Convert Variant IDs to Variant Paths ⭐️
        
        selected_variant_paths = None
        if selected_variant_ids: # Check if the list is not empty
            # Convert list of strings ['7', '6'] to list of integers [7, 6]
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            
            # Query the database for the corresponding variant_path strings
            variant_objects = ProcessVariant.objects.filter(
                id__in=variant_ids, # This correctly handles multiple IDs
                project=project
            )
            # Extract the actual variant_path strings
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            
            if not selected_variant_paths:
                # If IDs were requested but none were found/valid, pass an empty list
                selected_variant_paths = []
        
        # --- 3. Filter the Event Log ---
        # Pass the extracted parameters and the variant paths to the filtering function
        log_data = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # This is usually the column containing the variant path
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths, # 👈 Using the retrieved paths here
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # --- 4. Calculate KPIs on the Filtered Log ---
        event_log_data = log_data.to_dict('records')
        
        result = get_minimum_cycle_time_hours(
            event_log_data,
            columns.case_id,
            columns.activity,
            columns.timestamp_start,
            columns.timestamp_end,
            office_start_hour=6,
            office_end_hour=18
        )
        
        
        result_data = json.loads(result)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        return Response({"error": "Project matching query does not exist."}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown" 
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:       
        return Response({"error": str(e)}, status=500)
    



@api_view(['GET'])
def time_series_cycle_time_metrics(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        aggregation_level = request.query_params.get('aggregation_level', 'month') 
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')
        
        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)           
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup (from previous successful implementation) ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = [] # Ensure an empty list if lookup fails

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Assumed to be the activity column for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            return Response({"error": "Filtering resulted in an empty event log. Please check your filter criteria."}, status=200)

        # 5. Call the time series calculation function on the FILTERED data
        event_log_data = df_filtered.to_dict('records')

        result_json_string = get_cycle_time_over_period(
            event_log_data,
            columns.case_id,
            start_time_col=columns.timestamp_start,
            complete_time_col=columns.timestamp_end,
            office_start_hour=6,
            office_end_hour=18,
            aggregation_level=aggregation_level,
            # NOTE: We no longer pass start/end_date_filter here, 
            # as the data is already filtered by date.
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(result_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        # Define file_path for error reporting if it failed earlier
        file_path = "Unknown" 
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:       
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def total_case_count(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return 0 case count gracefully
            return Response({"total_cases": 0, "error": "Filtering resulted in zero cases."}, status=200)

        # 5. Calculate the total cases on the FILTERED data
        # NOTE: If calculate_total_cases expects a list of dicts, convert the filtered DataFrame
        event_log_data = df_filtered.to_dict('records')
        
        # Since the data is already filtered, we don't pass the date filters again.
        case_count_json_string = calculate_total_cases(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            start_time_col=columns.timestamp_start,      
            complete_time_col=columns.timestamp_end,     
            # start_date_filter and end_date_filter are NOT needed here
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(case_count_json_string)
        
        return Response(result_data) 
        
    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def average_idle_time_view(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return 0 idle time gracefully
            return Response({"total_idle_time": 0.0, "error": "Filtering resulted in zero cases."}, status=200)

        # 5. Calculate total idle time on the FILTERED data
        # NOTE: The idle time function relies on the office hours defined here
        event_log_data = df_filtered.to_dict('records')

        idle_time_json_string = get_average_idle_time_hours(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            start_time_col=columns.timestamp_start,
            complete_time_col=columns.timestamp_end,
            office_start_hour=6,
            office_end_hour=18
        )
       
        
        # 6. Parse and Return Response
        result_data = json.loads(idle_time_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def total_idle_time(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return 0 idle time gracefully
            return Response({"total_idle_time": 0.0, "error": "Filtering resulted in zero cases."}, status=200)

        # 5. Calculate total idle time on the FILTERED data
        # NOTE: The idle time function relies on the office hours defined here
        event_log_data = df_filtered.to_dict('records')

        idle_time_json_string = calculate_average_idle_time_metrics(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            start_time_col=columns.timestamp_start,
            complete_time_col=columns.timestamp_end,
            office_start_hour=6,
            office_end_hour=18
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(idle_time_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def loops_and_ratio(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return 0 loops/ratios gracefully
            return Response({"total_loops": 0, "looping_case_ratio": 0.0, "error": "Filtering resulted in zero cases."}, status=200)

        # 5. Calculate loop metrics on the FILTERED data
        event_log_data = df_filtered.to_dict('records')

        total_loops_ratio = calculate_loop_metrics(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity # Pass the activity column (used as the variant_col in filter)
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(total_loops_ratio)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e: 
        return Response({"error": str(e)}, status=500)



@api_view(['GET'])
def bottleneck_and_ratio(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return placeholder values for bottleneck metrics gracefully
            return Response({
                "bottleneck_activity": "N/A", 
                "bottleneck_duration_sum": 0.0,
                "error": "Filtering resulted in zero cases."
            }, status=200)

        # 5. Calculate bottleneck metrics on the FILTERED data
        event_log_data = df_filtered.to_dict('records')

        result_json_string = calculate_bottleneck_metrics(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            start_time_col=columns.timestamp_start,
            complete_time_col=columns.timestamp_end
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(result_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def largest_bottleneck_view(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return placeholder values for bottleneck metrics gracefully
            return Response({
                "bottleneck_activity": "N/A", 
                "bottleneck_duration_sum": 0.0,
                "error": "Filtering resulted in zero cases."
            }, status=200)

        # 5. Calculate bottleneck metrics on the FILTERED data
        event_log_data = df_filtered.to_dict('records')

        result_json_string = calculate_largest_bottlenecks(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            start_time_col=columns.timestamp_start,
            complete_time_col=columns.timestamp_end,
            office_start_hour=6,
            office_end_hour=18,
            top_n=3

        )
      
        # 6. Parse and Return Response
        result_data = json.loads(result_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    


@api_view(['GET'])
def cal_step_and_cases(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return placeholder values (0 steps, 0 cases) gracefully
            return Response({
                "avg_steps_per_case": 0.0, 
                "total_cases_analyzed": 0,
                "total_steps": 0,
                "error": "Filtering resulted in zero cases."
            }, status=200)

        # 5. Calculate steps per case metrics on the FILTERED data
        event_log_data = df_filtered.to_dict('records')

        result_json_string = calculate_steps_per_case_metrics(
            event_log_data=event_log_data,
            case_id_col=columns.case_id
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(result_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:  
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def dropout_rate(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        # Note: We need the start timestamp for date filtering, even if the dropout function doesn't explicitly use it.
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return 0 dropout rate gracefully
            return Response({
                "dropout_rate": 0.0, 
                "completed_cases": 0,
                "total_cases_analyzed": 0,
                "error": "Filtering resulted in zero cases."
            }, status=200)

        # 5. Calculate dropout rate on the FILTERED data
        event_log_data = df_filtered.to_dict('records')

        result_json_string = calculate_dropout_rate(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            complete_time_col=columns.timestamp_end
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(result_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    



@api_view(['GET'])
def average_activity_time(request, pk=None):
    project_id = pk
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # --- 2. Setup and Load Data ---
        project = Project.objects.get(pk=pk)
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup (Crucial step for variants filter) ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = []
        
        # --- 3. Apply ALL Filters using the standard function ---
        filtered_df_log = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity,
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths,
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check for empty log after filtering
        if filtered_df_log.empty:
            # Return an empty list or appropriate placeholder gracefully
            return Response({
                "error": "Filtering resulted in zero events.", 
                "average_activity_durations": []
            }, status=200)


        # --- 4. Calculation ---
        event_log_data = filtered_df_log.to_dict('records')

        result = calculate_average_activity_duration(
            event_log_data=event_log_data, 
            activity_col=columns.activity, 
            start_time_col=columns.timestamp_start, 
            complete_time_col=columns.timestamp_end,
            office_start_hour=6,
            office_end_hour=18
        )
        
        result_data = json.loads(result)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project not found for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": "CSV file not found."}, status=404) 
    except Exception as e:
        # NOTE: Print statement is good for debugging, but we remove it for the final response structure
        return Response({"error": f"An internal server error occurred: {str(e)}"}, status=500)



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
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # NOTE: We intentionally skip the 'variants' lookup and filter logic 
        # because the goal is to CALCULATE the top variants.

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data
        df_log = pd.read_csv(file_path)

        # ⭐️ 4. FILTER THE EVENT LOG (Date and Cycle Time Only) ⭐️
        # We pass selected_variants=None to skip the variant filtering step 
        # in the filter_event_log_pre_kpi function.
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Still needed for path calculation inside the filter function
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=None, # IMPORTANT: Skip variant filtering
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return an empty list gracefully
            return Response({"top_variants": [], "error": "Filtering resulted in zero cases."}, status=200)

        # 5. Calculate top variants on the FILTERED data
        event_log_data = df_filtered.to_dict('records')

        result_json_string = calculate_top_variants(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity, # Used for path calculation within calculate_top_variants
            complete_time_col=columns.timestamp_end, # Assuming this is used for case completion time
            top_n=10 
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(result_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)



@api_view(['GET'])
def first_pass_rate(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        # We perform the lookup to allow filtering if the user applies it
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths, # Applies the variant filter if present
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return 0.0 first pass rate gracefully
            return Response({
                "first_pass_rate": 0.0, 
                "total_cases_analyzed": 0,
                "error": "Filtering resulted in zero cases."
            }, status=200)

        # 5. Calculate first pass rate on the FILTERED data
        event_log_data = df_filtered.to_dict('records')

        result_json_string = calculate_first_pass_rate(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(result_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def longest_waiting_time(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths, # Applies the variant filter if present
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return placeholder values gracefully
            return Response({
                "longest_waiting_activity": "N/A", 
                "max_waiting_time": 0.0,
                "error": "Filtering resulted in zero cases."
            }, status=200)

        # 5. Calculate longest waiting time on the FILTERED data
        event_log_data = df_filtered.to_dict('records')

        result_json_string = calculate_longest_waiting_time_step(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            start_time_col=columns.timestamp_start,
            complete_time_col=columns.timestamp_end
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(result_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)



@api_view(['GET'])
def variant_complexity_index(request, pk=None):
    project_id = pk # Capture the ID for error logging
    try:
        # --- 1. Extract ALL query parameters ---
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        # Filters for the inner-case cycle time (if provided)
        min_cycle_time_str = request.query_params.get('min_cycle_time', None)
        max_cycle_time_str = request.query_params.get('max_cycle_time', None)
        min_cycle_time = float(min_cycle_time_str) if min_cycle_time_str else None
        max_cycle_time = float(max_cycle_time_str) if max_cycle_time_str else None
        
        # Variant Filters (using getlist for multiple selections)
        selected_variant_ids = request.query_params.getlist('variants')

        # 2. Fetch Project and Column Definitions
        project = Project.objects.get(pk=project_id) 
        
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        
        # 3. Load Data & Variant Path Lookup
        df_log = pd.read_csv(file_path)

        # ⭐️ Variant Path Lookup ⭐️
        selected_variant_paths = None
        if selected_variant_ids: 
            variant_ids = [int(id) for id in selected_variant_ids if id.isdigit()]
            variant_objects = ProcessVariant.objects.filter(id__in=variant_ids, project=project)
            selected_variant_paths = list(variant_objects.values_list('variant_path', flat=True))
            if not selected_variant_paths:
                selected_variant_paths = []

        # ⭐️ 4. FILTER THE EVENT LOG ⭐️
        df_filtered = filter_event_log_pre_kpi(
            df=df_log,
            case_id_col=columns.case_id,
            variant_col=columns.activity, # Used for path calculation
            timestamp_start_col=columns.timestamp_start,
            timestamp_complete_col=columns.timestamp_end, 
            start_date=start_date,
            end_date=end_date,
            selected_variants=selected_variant_paths, # Applies the variant filter if present
            min_cycle_time=min_cycle_time,
            max_cycle_time=max_cycle_time,
            time_unit="hours"
        )
        
        # Check if filtering resulted in an empty log
        if df_filtered.empty:
            # Return 0.0 complexity gracefully
            return Response({
                "complexity_index": 0.0,
                "error": "Filtering resulted in zero cases."
            }, status=200)

        # 5. Calculate complexity index on the FILTERED data
        event_log_data = df_filtered.to_dict('records')

        result_json_string = calculate_variant_complexity_index(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            complete_time_col=columns.timestamp_end
        )
        
        # 6. Parse and Return Response
        result_data = json.loads(result_json_string)
        
        return Response(result_data) 

    except Project.DoesNotExist:
        error_msg = f"Project matching query does not exist for ID: {project_id}."
        return Response({"error": error_msg}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        file_path = "Unknown"
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
            time_period='M' # 'D' for Daily, 'W' for Weekly, 'M' for Monthly
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

        result = calculate_average_time_saved_potential(
            event_log_data, 
            columns.case_id, 
            columns.timestamp_start, 
            columns.timestamp_end,
            office_start_hour=6,
            office_end_hour=18
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

        result = calculate_total_completed_cases(event_log_data, 
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
 
        result = calculate_case_throughput_and_dropouts(
            event_log_data, 
            columns.case_id,
            columns.activity,
            columns.timestamp_start, 
            columns.timestamp_end,
            period='M' # 'D' for Day, 'W' for Week, 'M' for Month
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
    


# @api_view(['GET'])
# def actual_path_data_with_connections(request, pk=None):
#     try:
#         time_param = request.query_params.get('time', None)
#         project = Project.objects.get(pk=pk) 
#         if project.user != request.user:
#             return Response({"error": "You do not have permission to access this project."}, status=403)
        
#         columns = DefineColumns.objects.get(project=project)           
#         file_path = project.csv_file.path
#         df_log = pd.read_csv(file_path)
  
#         event_log_data = df_log.to_dict('records')
 
#         result = analyze_and_structure_process_datas(
#             event_log_data, 
#             columns.case_id, 
#             columns.activity,
#             columns.timestamp_start,
#             columns.timestamp_end,
#             project=pk
            
#         )
#         result_data = json.loads(result)
        
#         return Response(result_data) 

#     except DefineColumns.DoesNotExist:
#         return Response({"error": "Column definitions not found for this project."}, status=404)
#     except FileNotFoundError:
#         return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
#     except Exception as e:       
#         return Response({"error": str(e)}, status=500)



@api_view(['GET'])
def actual_path_data_with(request, pk=None):
    try:
        project = Project.objects.get(pk=pk)

        if project.user != request.user:
            return Response(
                {"error": "You do not have permission to access this project."},
                status=403
            )

        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        event_log_data = df_log.to_dict('records')
        result = analyze_and_structure_process_datas(
            event_log_data,
            columns.case_id,
            columns.activity,
            columns.timestamp_start,
            columns.timestamp_end,
            project=project,
        )
        result_data = json.loads(result)

        if "global_metrics" in result_data:
            result_data["global_metrics"]["happy_path"] = columns.happy_path
        else:
            result_data["global_metrics"] = {"happy_path": columns.happy_path}

        return Response(result_data)

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Project.DoesNotExist:
        return Response({"error": f"Project not found for id {pk}."}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)




# @api_view(['GET'])
# def actual_path_data_with_problems(request, pk=None):
#     try:
#         time_param = request.query_params.get('time', None)
#         project = Project.objects.get(pk=pk) 
#         if project.user != request.user:
#             return Response({"error": "You do not have permission to access this project."}, status=403)
        
#         columns = DefineColumns.objects.get(project=project)           
#         file_path = project.csv_file.path
#         df_log = pd.read_csv(file_path)
  
#         event_log_data = df_log.to_dict('records')
 
#         result = analyze_and_structure_process_data(
#             event_log_data, 
#             columns.case_id, 
#             columns.activity,
#             columns.timestamp_start,
#             columns.timestamp_end
            
#         )
#         result_data = json.loads(result)
        
#         return Response(result_data) 

#     except DefineColumns.DoesNotExist:
#         return Response({"error": "Column definitions not found for this project."}, status=404)
#     except FileNotFoundError:
#         return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
#     except Exception as e:       
#         return Response({"error": str(e)}, status=500)
    


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



from .fil import *
from .ai import generate_complete_kpi_package_openai

@api_view(['GET'])
def kpi_summary_metrics(request, pk=None):
    project_id = pk
    response_data = {}

    try:

        project = Project.objects.get(pk=project_id)

        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)

        columns = DefineColumns.objects.get(project=project)

        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)

        current_kpi_json = generate_project_report(
            df=df_log,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            start_col=columns.timestamp_start,
            end_col=columns.timestamp_end,
        )

        project_metadata = {
            "project_id": project.pk,
            "process_name": project.process,
            "department": getattr(project.department, "name", "N/A"),
            "team": getattr(project.team, "name", "N/A"),
        }

        response_data["Current_Project_Data"] = {
            "Metadata": project_metadata,
            "KPIs": json.loads(current_kpi_json),
        }

   
        response_data["Related_Project_Data"] = None

        if project.related_project:
            related_project = project.related_project
            related_project_id = related_project.pk

            try:
                related_columns = DefineColumns.objects.get(project=related_project)
                related_df = pd.read_csv(related_project.csv_file.path)

                related_kpi_json = generate_project_report(
                    df=related_df,
                    case_id_col=related_columns.case_id,
                    activity_col=related_columns.activity,
                    start_col=related_columns.timestamp_start,
                    end_col=related_columns.timestamp_end,
                )

                related_metadata = {
                    "project_id": related_project.pk,
                    "process_name": related_project.process,
                    "department": getattr(related_project.department, "name", "N/A"),
                    "team": getattr(related_project.team, "name", "N/A"),
                }

                response_data["Related_Project_Data"] = {
                    "Metadata": related_metadata,
                    "KPIs": json.loads(related_kpi_json),
                }

            except DefineColumns.DoesNotExist:
                response_data["Related_Project_Data"] = {
                    "error": f"Column definitions missing for related project ID {related_project_id}"
                }
            except FileNotFoundError:
                response_data["Related_Project_Data"] = {"error": "CSV file not found for related project"}
            except Exception as e:
                response_data["Related_Project_Data"] = {"error": f"Error processing related project: {str(e)}"}

        ai_summary = generate_complete_kpi_package_openai(response_data)

        # 7️⃣ Return full AI response
        return Response(ai_summary)

    except Project.DoesNotExist:
        return Response({"error": f"Project not found for ID {project_id}."}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found for project ID {project_id}."}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)




@api_view(['GET'])
def process_variants(request, pk=None):
    try:
        time_param = request.query_params.get('time', None)
        project = Project.objects.get(pk=pk) 
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)
        
        columns = DefineColumns.objects.get(project=project)           
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)
  
        event_log_data = df_log.to_dict('records')
 
        result = calculate_variants_and_metrics(
            event_log_data,              # List of event dictionaries
            columns.case_id,                 # 'case_id' column name
            columns.activity,                # 'activity' column name
            columns.timestamp_start,         # 'timestamp_start' column name
            columns.timestamp_end,      # Optional: 'timestamp_end' column name (needed for cycle time)
            time_unit='hours'            # Unit for cycle time calculation
)
        result_data = json.loads(result)
        
        return Response(result_data) 

    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": f"CSV file not found at path: {file_path}"}, status=404)
    except Exception as e:       
        return Response({"error": str(e)}, status=500)
    

from .kpi_banchmark import generate_project_report

@api_view(['GET'])
def project_report(request, pk):
    project = Project.objects.get(pk=pk)
    columns = DefineColumns.objects.get(project=project)
    df = pd.read_csv(project.csv_file.path)

    report_json = generate_project_report(
        df,
        case_id_col=columns.case_id,
        activity_col=columns.activity,
        start_col=columns.timestamp_start,
        end_col=columns.timestamp_end
    )

    return Response(json.loads(report_json))



@api_view(['GET'])
def cost_per_process_view(request, pk=None):
    
    try:
        project = Project.objects.get(pk=pk)
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)

        columns = DefineColumns.objects.get(project=project)
        file_path = project.csv_file.path
        df_log = pd.read_csv(file_path)
        event_log_data = df_log.to_dict('records')

        result_json = calculate_cost_per_process(
            event_log_data=event_log_data,
            activity_col=columns.activity,
            start_time_col=columns.timestamp_start,
            complete_time_col=columns.timestamp_end,
            project=project
        )

        result_data = json.loads(result_json)
        return Response(result_data)

    except Project.DoesNotExist:
        return Response({"error": f"Project not found for id {pk}."}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": "CSV file not found for this project."}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)
    



@api_view(['GET'])
def average_deviation_view(request, pk=None):
    
    try:
        project = Project.objects.get(pk=pk)
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)

        columns = DefineColumns.objects.get(project=project)
        df_log = pd.read_csv(project.csv_file.path)
        event_log_data = df_log.to_dict('records')

        result_json = calculate_average_deviation_from_happy_path(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            start_time_col=columns.timestamp_start,
            complete_time_col=columns.timestamp_end,
            project=project
        )

        result_data = json.loads(result_json)
        return Response(result_data, status=200)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)
    



@api_view(['GET'])
def happy_path_compliance_view(request, pk=None):
   
    try:
        project = Project.objects.get(pk=pk)
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)

        columns = DefineColumns.objects.get(project=project)
        df = pd.read_csv(project.csv_file.path)
        event_log_data = df.to_dict('records')

        result_json = calculate_happy_path_compliance_rate(
            event_log_data=event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            project=project
        )

        result_data = json.loads(result_json)
        return Response(result_data, status=200)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)
    



@api_view(['POST'])
def simulate_actual_path_view(request, pk=None):
    text = request.data.get('text', {})
    id = request.data.get('project_id', None)
    print("Received data for simulation:", text)
    print("Received id:", id)
    if not id or not text:        
        return Response({"error": "ID & TEXT are required in the request body."}, status=400)
    
    try:
        project = Project.objects.get(pk=id)
        if project.user != request.user:
            return Response({"error": "Permission denied"}, status=403)

        columns = DefineColumns.objects.get(project=project)
        df = pd.read_csv(project.csv_file.path)
        event_log_data = df.to_dict("records")

        n_sim = int(request.query_params.get("n", 500))
        variation = float(request.query_params.get("variation", 0.2))

        
        result_json = simulate_actual_process(
            event_log_data,
            case_id_col=columns.case_id,
            activity_col=columns.activity,
            start_col=columns.timestamp_start,
            end_col=columns.timestamp_end,
            n_simulations=n_sim,
            variation=variation
        )

        return Response(json.loads(result_json), status=200)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)
    


from django.http import FileResponse
from .reports import generate_kpi_benchmark_pdf



@api_view(['POST'])
def export_kpi_benchmark_pdf(request, pk=None):
    """
    Endpoint to export KPI Benchmark JSON into a styled PDF.
    Example frontend call: POST /api/project/export-benchmark-pdf/
    """
    try:
        data = request.data  # Expect JSON payload like your KPI summary

        pdf_buffer = generate_kpi_benchmark_pdf(data)
        response = FileResponse(pdf_buffer, as_attachment=True, filename="Process_Benchmark_Report.pdf")
        return response

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)
 
from .simulation import simulate_process_analysis
from django.shortcuts import get_object_or_404
from .ai import parse_process_intent


@api_view(['POST'])
def simulate_process_view(request, pk):
    """
    POST: Simulate process improvement for a project.
    Accepts JSON body parameters like:
    {
        "remove_bottlenecks": true,
        "remove_loops": false,
        "remove_dropouts": true,
        "target_activity": "Payment Monitoring"
    }
    """
    try:
        # ---- 1. Get project ----
        project = get_object_or_404(Project, pk=pk, user=request.user)

        # ---- 2. Extract simulation parameters from request body ----
        # remove_bottlenecks = request.data.get("remove_bottlenecks", False)
        # remove_loops = request.data.get("remove_loops", False)
        # remove_dropouts = request.data.get("remove_dropouts", False)
        # target_activity = request.data.get("target_activity")
        text = request.data.get('text')
        process = request.data.get('selected', None)
        parameter = parse_process_intent(text)       
        remove_bottlenecks = parameter['remove_bottlenecks']
        remove_loops = parameter['remove_loops']
        remove_dropouts = parameter['remove_dropouts']
        # ---- 3. Run simulation ----
        # simulated_result = None
        simulated_result = simulate_process_analysis(
            project=project,
            remove_bottlenecks=remove_bottlenecks,
            remove_loops=remove_loops,
            remove_dropouts=remove_dropouts,
            target_activity=process
        )

        # ---- 4. Return simulation result ----
        return Response(
            {
                "message": "Process simulation completed successfully.",
                "project_id": project.id,
                "process_name": project.process,
                "simulation_result": simulated_result
            },
            status=status.HTTP_200_OK
        )

    except Project.DoesNotExist:
        return Response({"error": "Project not found."}, status=status.HTTP_404_NOT_FOUND)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column mapping not defined for this project."}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        import traceback; traceback.print_exc()
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




def to_visual_nodes(process_nodes):
    """
    Pure transformer:
    Takes analyzer's `process_flow_nodes` and returns the UI-friendly array.
    No DB access. No column mapping. No file reading.
    """
    if not isinstance(process_nodes, list):
        return []

    visual = []
    seen = set()

    for node in process_nodes:
        node_id = str(node.get("id", "")).strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)

        # value → string with 2 decimals
        raw_val = node.get("value", "0")
        try:
            v = float(raw_val)
            val_str = f"{v:.2f}"
        except Exception:
            val_str = "0.00"

        entry = {
            "id": node_id,
            "label": node.get("label", "Unknown"),
            "value": val_str,
            "status": node.get("status", "in-progress"),
            "owner": node.get("owner", "Process Team"),
            "descriptions": node.get("descriptions", []),
            "isBottleneck": bool(node.get("isBottleneck", False)),
            "hasLoop": bool(node.get("hasLoop", False)),
            "isDropout": bool(node.get("isDropout", False)),
        }

        # loop connections if present
        if node.get("loopConnections"):
            entry["loopConnections"] = node["loopConnections"]

        # optional extras (nice for UI badges)
        extras = []
        if entry["isBottleneck"]:
            extras.append({
                "id": f"{node_id}a",
                "label": f"{entry['label']} Review",
                "position": "right"
            })
        if entry["hasLoop"]:
            extras.append({
                "id": f"{node_id}b",
                "label": f"{entry['label']} Rework",
                "position": "left",
                "hasLoop": True,
                "loopConnections": entry.get("loopConnections")
            })
        entry["extras"] = extras

        visual.append(entry)

    return visual


@api_view(['GET'])
def process_visual_view(request, pk=None):
    """
    GET /api/project/process-visual-view/<pk>/
    - Reads DefineColumns for the project
    - Loads the CSV
    - Calls your utils analyzer with the mapped column names
    - Returns a UI-friendly array for graphing (no hard-coded columns)
    """
    try:
        # 1) Project + permission
        project = Project.objects.get(pk=pk)
        if project.user != request.user:
            return Response({"error": "You do not have permission to access this project."}, status=403)

        # 2) Column mapping from DB (this is what you wanted in the view)
        cols = DefineColumns.objects.get(project=project)
        case_col = cols.case_id
        act_col = cols.activity
        start_col = cols.timestamp_start
        end_col = cols.timestamp_end

        # 3) Load CSV
        df = pd.read_csv(project.csv_file.path)

        # 4) Convert to list[dict] and call your analyzer (UTILS)
        event_log_data = df.to_dict("records")
        analysis_json = analyze_and_structure_process(
            event_log_data=event_log_data,
            case_id_col=case_col,
            activity_col=act_col,
            start_time_col=start_col,
            complete_time_col=end_col
        )

        # 5) Parse analyzer output
        try:
            analysis = json.loads(analysis_json)
        except Exception:
            return Response({"error": "Analyzer returned invalid JSON."}, status=500)

        # If analyzer returns an error payload
        if isinstance(analysis, dict) and "Error" in analysis:
            return Response({"error": analysis["Error"]}, status=400)

        # 6) Extract nodes and transform
        if not isinstance(analysis, dict) or "process_flow_nodes" not in analysis:
            return Response({"error": "Analyzer did not return process_flow_nodes."}, status=400)

        nodes = analysis["process_flow_nodes"]
        visual_array = to_visual_nodes(nodes)

        return Response({
            "project_id": project.id,
            "visual_data_count": len(visual_array),
            "visual_data": visual_array
        }, status=200)

    except Project.DoesNotExist:
        return Response({"error": f"Project {pk} not found."}, status=404)
    except DefineColumns.DoesNotExist:
        return Response({"error": "Column definitions not found for this project."}, status=404)
    except FileNotFoundError:
        return Response({"error": "CSV file not found for this project."}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)