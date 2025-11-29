import pandas as pd
import json
from datetime import datetime, timedelta
# Assuming these are defined in your project (e.g., from .models import Project, DefineColumns)
from rest_framework.decorators import api_view
from rest_framework.response import Response


# ====================================================================
# A. HELPER FUNCTIONS (UTILITIES)
# ====================================================================

def parse_duration_to_timedelta(duration_str):
    """Converts a string like '1h 30min' to a timedelta object."""
    if not duration_str:
        return None
    
    duration_str = duration_str.strip().lower().replace(' ', '')
    total_seconds = 0
    
    try:
        if 'h' in duration_str:
            h_part, duration_str = duration_str.split('h', 1)
            if h_part: total_seconds += int(h_part) * 3600
        
        if 'min' in duration_str:
            min_part, duration_str = duration_str.split('min', 1)
            if min_part: total_seconds += int(min_part) * 60
    except ValueError: 
        return None
        
    return timedelta(seconds=total_seconds)


def calculate_variants(df, case_id_col, activity_col, start_time_col):
    """Calculates the variant string and assigns a simple 'variant_label' (A, B, C) to each event."""
    
    # 1. Ensure events are sorted by time within each case
    df = df.sort_values(by=[case_id_col, start_time_col])

    # 2. Group by case and join activity names into a unique sequence string
    variant_df = df.groupby(case_id_col)[activity_col].apply(
        lambda x: ' > '.join(x)
    ).reset_index()
    variant_df.rename(columns={activity_col: 'full_variant_string'}, inplace=True)
    
    # 3. Map unique variant strings to simple labels (A, B, C, ...)
    unique_variants = variant_df['full_variant_string'].unique()
    # Maps the unique sequence strings to 'A', 'B', 'C', etc.
    variant_map = {variant: label for label, variant in zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ', unique_variants)}
    
    variant_df['variant_label'] = variant_df['full_variant_string'].map(variant_map)
    
    # 4. Merge the simple label back to the main DataFrame (df)
    df = df.merge(variant_df[[case_id_col, 'variant_label']], on=case_id_col, how='left')
    return df


def apply_process_mining_filters(df_log: pd.DataFrame, request_params: dict, column_map: dict) -> pd.DataFrame:
    """Applies all date, cycle time, and variant filters sequentially."""
    
    # Map Columns
    CASE_ID = column_map.get('case_id')
    TIMESTAMP_START = column_map.get('timestamp_start')
    TIMESTAMP_END = column_map.get('timestamp_end')

    # Ensure timestamp columns are in datetime format
    for col in [TIMESTAMP_START, TIMESTAMP_END]:
        if col and col in df_log.columns:
            df_log[col] = pd.to_datetime(df_log[col], errors='coerce', utc=True)
            
    # --- 1. DATE RANGE FILTER ---
    # Using 'date_range_start/end' as per best practice (and matching UI intent)
    start_date_str = request_params.get('date_range_start') 
    end_date_str = request_params.get('date_range_end')     
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
            date_filter = (df_log[TIMESTAMP_START].dt.date >= start_date) & \
                          (df_log[TIMESTAMP_START].dt.date <= end_date)
            df_log = df_log[date_filter].copy()
        except (ValueError, KeyError):
            pass

    # --- 2. CYCLE TIME FILTER (Case-level) ---
    min_cycle_time_str = request_params.get('min_cycle_time') 
    max_cycle_time_str = request_params.get('max_cycle_time') 
    
    min_td = parse_duration_to_timedelta(min_cycle_time_str)
    max_td = parse_duration_to_timedelta(max_cycle_time_str)

    if (min_td is not None or max_td is not None) and CASE_ID and TIMESTAMP_START and TIMESTAMP_END:
        
        case_cycle_times = df_log.groupby(CASE_ID).agg(
            first_start=(TIMESTAMP_START, 'min'),
            last_end=(TIMESTAMP_END, 'max')
        )
        case_cycle_times['cycle_time'] = case_cycle_times['last_end'] - case_cycle_times['first_start']
        
        cases_to_keep = pd.Series(True, index=case_cycle_times.index)
        if min_td is not None:
            cases_to_keep &= (case_cycle_times['cycle_time'] >= min_td)
        if max_td is not None:
            cases_to_keep &= (case_cycle_times['cycle_time'] <= max_td)
            
        filtered_case_ids = cases_to_keep[cases_to_keep].index
        
        df_log = df_log[df_log[CASE_ID].isin(filtered_case_ids)].copy()

    # --- 3. PROCESS VARIANT FILTER (Case-level) ---
    selected_variants = request_params.getlist('process_variants') 
    
    # Requires the 'variant_label' column created by calculate_variants()
    if selected_variants and 'Activity' in df_log.columns:
         df_log = df_log[df_log['activity'].isin(selected_variants)].copy()

    return df_log



# import pandas as pd
# from datetime import datetime, timedelta

# def parse_duration_to_timedelta(duration_str):
#     """Converts a string like '1h 30min' to a timedelta object."""
#     if not duration_str:
#         return None
    
#     duration_str = duration_str.strip().lower().replace(' ', '')
#     total_seconds = 0
    
#     try:
#         if 'h' in duration_str:
#             h_part, duration_str = duration_str.split('h', 1)
#             if h_part: total_seconds += int(h_part) * 3600
        
#         if 'min' in duration_str:
#             min_part, duration_str = duration_str.split('min', 1)
#             if min_part: total_seconds += int(min_part) * 60
#     except ValueError: 
#         return None # Return None for malformed strings
        
#     return timedelta(seconds=total_seconds)



# def apply_process_mining_filters(df_log: pd.DataFrame, request_params: dict, column_map: dict) -> pd.DataFrame:    
    
#     CASE_ID = column_map.get('case_id')
#     TIMESTAMP_START = column_map.get('timestamp_start')
#     TIMESTAMP_END = column_map.get('timestamp_end')

#     # Ensure timestamp columns are in datetime format
#     for col in [TIMESTAMP_START, TIMESTAMP_END]:
#         if col and col in df_log.columns:
#             df_log[col] = pd.to_datetime(df_log[col], errors='coerce', utc=True)
            
#     # --- 2. DATE RANGE FILTER ---
#     start_date_str = request_params.get('start_date') 
#     end_date_str = request_params.get('end_date')     
    
#     if start_date_str and end_date_str:
#         try:
#             start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
#             end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
#             # Filter events based on the event start date
#             date_filter = (df_log[TIMESTAMP_START].dt.date >= start_date) & \
#                           (df_log[TIMESTAMP_START].dt.date <= end_date)
#             df_log = df_log[date_filter].copy()
#         except (ValueError, KeyError):
#             # KeyErrors might occur if the column doesn't exist
#             pass 

#     # --- 3. CYCLE TIME FILTER ---
#     min_cycle_time_str = request_params.get('min_cycle_time') 
#     max_cycle_time_str = request_params.get('max_cycle_time') 
    
#     min_td = parse_duration_to_timedelta(min_cycle_time_str)
#     max_td = parse_duration_to_timedelta(max_cycle_time_str)

#     if (min_td is not None or max_td is not None) and CASE_ID and TIMESTAMP_START and TIMESTAMP_END:
        
#         # Calculate case cycle times
#         case_cycle_times = df_log.groupby(CASE_ID).agg(
#             first_start=(TIMESTAMP_START, 'min'),
#             last_end=(TIMESTAMP_END, 'max')
#         )
#         case_cycle_times['cycle_time'] = case_cycle_times['last_end'] - case_cycle_times['first_start']
        
#         # Determine the cases to keep
#         cases_to_keep = pd.Series(True, index=case_cycle_times.index)
        
#         if min_td is not None:
#             cases_to_keep &= (case_cycle_times['cycle_time'] >= min_td)
            
#         if max_td is not None:
#             cases_to_keep &= (case_cycle_times['cycle_time'] <= max_td)
            
#         filtered_case_ids = cases_to_keep[cases_to_keep].index
        
#         # Filter the current DataFrame by the qualifying Case IDs
#         df_log = df_log[df_log[CASE_ID].isin(filtered_case_ids)].copy()

#     # --- 4. PROCESS VARIANT FILTER ---
#     # Note: Using .getlist() is standard for multi-select checkboxes in Django
#     selected_variants = request_params.getlist('process_variants') 
    
#     # This assumes your DataFrame has a column named 'variant_label' 
#     # that matches the UI labels ('A', 'B', 'C', etc.).
#     if selected_variants and 'variant_label' in df_log.columns:
#          df_log = df_log[df_log['variant_label'].isin(selected_variants)].copy()

#     return df_log


import pandas as pd
import json

def calculate_variants_and_metrics(
    event_log_data,              # List of event dictionaries
    case_id_col,                 # 'case_id' column name
    activity_col,                # 'activity' column name
    timestamp_start_col,         # 'timestamp_start' column name
    timestamp_end_col=None,      # Optional: 'timestamp_end' column name (needed for cycle time)
    time_unit='hours',           # Unit for cycle time calculation
    top_n=5                   # Optional: Integer to limit results to top N variants
):
    """
    Calculates all unique process variants, their frequency, and median cycle time,
    returning only the top N variants by case count if top_n is specified.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        required_cols = [case_id_col, activity_col, timestamp_start_col]
        # Handle optional timestamp_end_col
        if timestamp_end_col and timestamp_end_col not in df.columns:
             df[timestamp_end_col] = df[timestamp_start_col]

        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        # 1. Prepare Timestamps and calculate total cases
        time_col_for_end = timestamp_end_col if timestamp_end_col and timestamp_end_col in df.columns else timestamp_start_col
        
        df[timestamp_start_col] = pd.to_datetime(df[timestamp_start_col], utc=True)
        df[time_col_for_end] = pd.to_datetime(df[time_col_for_end], utc=True)
        
        total_cases = df[case_id_col].nunique()

        # 2. Group by case ID to create the Variant and calculate cycle time components
        case_group = df.sort_values(timestamp_start_col).groupby(case_id_col)
        
        case_df = case_group.agg(
            Variant=(activity_col, lambda x: " -> ".join(x.astype(str))),
            Case_Start=(timestamp_start_col, 'min'),
            Case_End=(time_col_for_end, 'max')
        ).reset_index()

        # Calculate cycle time
        cycle_time_seconds = (case_df['Case_End'] - case_df['Case_Start']).dt.total_seconds()
        
        unit_conversion = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'days': 86400}
        divisor = unit_conversion.get(time_unit.lower(), 3600)
        
        case_df['Cycle_Time'] = cycle_time_seconds / divisor

        # 3. Aggregate by Variant to get case count and median cycle time
        variant_summary = case_df.groupby('Variant').agg(
            Case_Count=(case_id_col, 'count'),
            Median_Cycle_Time=('Cycle_Time', 'median'),
        ).reset_index()

        # --- KEY MODIFICATION FOR TOP VARIANTS ---
        
        # Sort by Case_Count descending (highest frequency first)
        variant_summary = variant_summary.sort_values(by='Case_Count', ascending=False)

        # Apply top_n filtering
        if isinstance(top_n, int) and top_n > 0:
            # Ensure we only keep the top N rows
            variant_summary = variant_summary.head(top_n)
            
        # 4. Calculate Frequency Percentage for the filtered set
        variant_summary['Frequency_pct'] = (variant_summary['Case_Count'] / total_cases) * 100

     
        results = []
        for _, row in variant_summary.iterrows():
            results.append({
                "variant": row['Variant'],
                "case_count": int(row['Case_Count']),
                "frequency_pct": round(row['Frequency_pct'], 2),
                f"median_cycle_time_{time_unit}": round(row['Median_Cycle_Time'], 2)
            })

        final_metrics = {
            "Total_Unique_Variants": len(results), 
            "Total_Cases_Analyzed": total_cases,
            "Variants": results
        }
        
        return json.dumps(final_metrics, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during variant analysis: {e}"}, indent=4)



import json
from .models import ProcessVariant

def save_process_variants(project, metrics_json):
    """
    Saves calculated variant metrics into the ProcessVariant model.
    
    Args:
        project (Project): Project instance to which these variants belong.
        metrics_json (str | dict): JSON string or dictionary output from calculate_variants_and_metrics().
    """
    # Ensure the input is a dictionary
    if isinstance(metrics_json, str):
        metrics = json.loads(metrics_json)
    else:
        metrics = metrics_json

    variants = metrics.get("Variants", [])

    # Optional: clean existing variants for the same project before inserting new ones
    ProcessVariant.objects.filter(project=project).delete()

    variant_objects = []
    for variant_data in variants:
        variant_objects.append(ProcessVariant(
            project=project,
            variant_path=variant_data.get("variant", ""),
            case_count=variant_data.get("case_count", 0),
            frequency_pct=variant_data.get("frequency_pct", 0.0),
            median_cycle_time_hours=variant_data.get("median_cycle_time_hours", None)
        ))

    # Bulk create for performance
    ProcessVariant.objects.bulk_create(variant_objects, ignore_conflicts=True)

    print(f"✅ Saved {len(variant_objects)} process variants for project: {project.process}")
