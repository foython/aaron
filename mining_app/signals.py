from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
import os
import json
from .models import Project, ProcessVariant
import pandas as pd
import json

def save_variants_for_project(project_id, variant_metrics_data):
    """
    Saves the variant analysis results to the ProcessVariant model.
    """
    try:
        project_instance = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return False, f"Project with ID {project_id} not found."

    variants = variant_metrics_data.get('Variants', [])
    
    # Delete previous analysis results before saving new ones
    if variants:
         ProcessVariant.objects.filter(project=project_instance).delete()
    
    variant_objects = []
    
    for data in variants:
        
        # Dynamically find the cycle time key (e.g., 'median_cycle_time_hours')
        cycle_time_key = next(
            (k for k in data.keys() if k.startswith("median_cycle_time_")), 
            None
        )
        cycle_time_value = data.get(cycle_time_key) if cycle_time_key else None
        
        variant_objects.append(
            ProcessVariant(
                project=project_instance,
                variant_path=data.get("variant"),
                case_count=data.get("case_count"),
                frequency_pct=data.get("frequency_pct"),
                median_cycle_time_hours=cycle_time_value
            )
        )

    # Use bulk_create for high performance
    if variant_objects:
        ProcessVariant.objects.bulk_create(variant_objects)
    
    return True, f"Successfully saved {len(variant_objects)} process variants for Project ID {project_id}."

from .fil import calculate_variants_and_metrics


# @receiver(post_save, sender=Project)
# def process_log_on_project_save(sender, instance, created, **kwargs):
#     """
#     Triggers process mining analysis whenever a new Project with a CSV file is saved.
#     """
#     # Only run if a new project is created AND a CSV file is present
#     if created and instance.csv_file:
#         print(f"Signal received: New Project {instance.pk} created with log file.")
        
#         # NOTE: For large files, this should be executed as an asynchronous task (e.g., Celery)
#         # to prevent blocking the web server.

#         # --- IMPORTANT: DEFINE LOG COLUMN NAMES HERE ---
#         # These constants must match the column headers in your uploaded CSV file.
#         CASE_ID_COL = 'case_id' 
#         ACTIVITY_COL = 'activity'
#         TIMESTAMP_START_COL = 'timestamp_start'
#         TIMESTAMP_END_COL = 'timestamp_end'
#         # -----------------------------------------------

#         try:
#             # 1. Read the uploaded CSV file into a Pandas DataFrame
#             file_path = instance.csv_file.path
            
#             # Read CSV. Add parameters like 'encoding' or 'sep' if needed.
#             log_df = pd.read_csv(file_path) 
            
#             # Convert DataFrame to the list of dictionaries format expected by the calculator
#             event_log_data = log_df.to_dict('records')

#             # 2. Run the process mining analysis
#             variant_metrics = calculate_variants_and_metrics(
#                 event_log_data,
#                 case_id_col=CASE_ID_COL,
#                 activity_col=ACTIVITY_COL,
#                 timestamp_start_col=TIMESTAMP_START_COL,
#                 timestamp_end_col=TIMESTAMP_END_COL,
#                 time_unit='hours',
#                 top_n=10 # Calculate and return only the top 10 variants
#             )
            
#             if "Error" in variant_metrics:
#                  # If the calculation function returns an error, raise it
#                  raise Exception(variant_metrics["Error"])

#             # 3. Save the results to the database
#             success, message = save_variants_for_project(instance.pk, variant_metrics)
            
#             # 4. Update the project status upon successful analysis
#             if success:
#                 # Use update_fields to prevent an infinite signal loop
#                 Project.objects.filter(pk=instance.pk).update(status=True) 

#             print(f"Analysis Status for Project {instance.pk}: {message}")

#         except Exception as e:
#             # Log the error and mark the project as failed
#             print(f"CRITICAL ERROR processing Project {instance.pk}: {e}")
#             Project.objects.filter(pk=instance.pk).update(status=False) # Ensure status is False if analysis fails