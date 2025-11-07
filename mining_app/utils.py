import pandas as pd
from datetime import timedelta
import json
import math
from .models import CostPerProcess

def calculate_net_working_time(start, end, start_h, end_h): return (end - start).total_seconds()
def robust_to_datetime(series, utc=True):
    if series.empty: return series
    try:
        dt_series = pd.to_datetime(series, errors='coerce', utc=utc)
        if dt_series.isnull().mean() < 0.01: return dt_series
    except Exception: pass
    dt_series = pd.to_datetime(series, format=None, errors='coerce', utc=utc, infer_datetime_format=True)
    if utc and not dt_series.dt.tz: dt_series = dt_series.dt.tz_localize('UTC', errors='coerce')
    return dt_series

def analyze_standard_path_performance_json(
    file_path,
    case_id_col='case_id',
    activity_col='activity',
    start_time_col='timestamp_start',
    complete_time_col='timestamp_complete'
):
    """
    Analyze standard (most frequent) process path and calculate average time per step.
    Automatically supports custom column names (like DefineColumns in your project).
    Returns JSON (list of steps with serial_number, activity_name, average_time_minutes).
    """
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Error reading file: {e}")
        return []

    # --- Auto-correct columns (flexible handling for naming differences) ---
    rename_map = {}

    # Normalize activity column
    if activity_col not in df.columns:
        possible_activity_cols = ["activity", "activity_name", "step", "task"]
        for col in possible_activity_cols:
            if col in df.columns:
                rename_map[col] = activity_col
                break

    # Normalize timestamp columns
    possible_start_cols = ["timestamp_start", "start_time", "StartTime", "begin"]
    possible_end_cols = ["timestamp_end", "timestamp_complete", "complete_time", "end_time", "finish"]

    if start_time_col not in df.columns:
        for col in possible_start_cols:
            if col in df.columns:
                rename_map[col] = start_time_col
                break

    if complete_time_col not in df.columns:
        for col in possible_end_cols:
            if col in df.columns:
                rename_map[col] = complete_time_col
                break

    # Normalize case_id
    if case_id_col not in df.columns:
        possible_case_cols = ["case_id", "Case ID", "case", "process_id"]
        for col in possible_case_cols:
            if col in df.columns:
                rename_map[col] = case_id_col
                break

    df.rename(columns=rename_map, inplace=True)

    # --- Validate required columns ---
    required = [case_id_col, activity_col, start_time_col, complete_time_col]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Columns found: {list(df.columns)}")

    # --- Calculate durations ---
    df[start_time_col] = pd.to_datetime(df[start_time_col])
    df[complete_time_col] = pd.to_datetime(df[complete_time_col])
    df["duration"] = df[complete_time_col] - df[start_time_col]

    # --- Find Most Frequent Path ---
    df_paths = df.groupby(case_id_col)[activity_col].apply(lambda x: " -> ".join(x)).reset_index()
    df_variants = df_paths[activity_col].value_counts().reset_index()
    df_variants.columns = ["Process Path (Variant)", "Frequency"]

    most_standard_path_string = (
        df_variants.sort_values(by="Frequency", ascending=False)
        .iloc[0]["Process Path (Variant)"]
    )
    standard_path_activities = [a.strip() for a in most_standard_path_string.split("->")]

    # --- Average Duration Per Step ---
    df_avg_time = df.groupby(activity_col)["duration"].mean().reset_index()
    df_avg_time.rename(columns={"duration": "Average Time (Duration)"}, inplace=True)

    df_filtered = df_avg_time[df_avg_time[activity_col].isin(standard_path_activities)].copy()
    df_filtered["order"] = pd.Categorical(
        df_filtered[activity_col],
        categories=standard_path_activities,
        ordered=True,
    )
    df_result = df_filtered.sort_values("order").drop(columns=["order"])

    # --- Convert to minutes ---
    df_result["average_time_minutes"] = (
        df_result["Average Time (Duration)"].dt.total_seconds() / 60
    ).round(2)
    df_result["serial_number"] = range(1, len(df_result) + 1)
    df_result.rename(columns={activity_col: "activity_name"}, inplace=True)

    # --- Final Output ---
    df_final = df_result[["serial_number", "activity_name", "average_time_minutes"]].copy()
    json_output = df_final.to_dict("records")

    return json.dumps(json_output, indent=4)


import pandas as pd
import json
from datetime import timedelta
import numpy as np


def calculate_net_working_time(start_dt, end_dt, start_hour, end_hour):
    
    total_seconds = 0
    current_dt = start_dt

    if start_dt >= end_dt:
        return 0

    while current_dt < end_dt:
        
        work_day_start = current_dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        work_day_end = current_dt.replace(hour=end_hour, minute=0, second=0, microsecond=0)

        if current_dt.weekday() in [5, 6] or current_dt >= work_day_end:
            current_dt += timedelta(days=1)
            while current_dt.weekday() in [5, 6]:
                current_dt += timedelta(days=1)
            current_dt = current_dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            continue

        if current_dt < work_day_start:
            current_dt = work_day_start
            continue

        effective_start = current_dt
        effective_end = min(end_dt, work_day_end)

        if effective_end > effective_start:
            total_seconds += (effective_end - effective_start).total_seconds()

        if effective_end == end_dt:
            break
        
        current_dt = effective_end 

    return total_seconds

def get_average_cycle_time_hours(
    event_log_data,
    case_id_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour
):
    """Calculate average cycle time (hours) considering working hours and weekends."""
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        case_start = df.groupby(case_id_col)[start_time_col].min().rename("Case_Start")
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename("Case_End")
        df_cycle = pd.merge(case_start, case_end, on=case_id_col)

        # Adjusted working time
        df_cycle["Working_Seconds"] = df_cycle.apply(
            lambda r: calculate_net_working_time(
                r["Case_Start"], r["Case_End"], office_start_hour, office_end_hour
            ),
            axis=1,
        )
        df_cycle["Cycle_Hours"] = df_cycle["Working_Seconds"] / 3600

        avg_hours = round(df_cycle["Cycle_Hours"].mean(), 2)
        return json.dumps(
            {"Average_Cycle_Time_Hours": avg_hours, "Total_Cases": len(df_cycle)},
            indent=4,
        )

    except Exception as e:
        return json.dumps({"Error": f"Failed to calculate average cycle time: {e}"}, indent=4)



def get_median_cycle_time_hours(
    event_log_data,
    case_id_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour
):
    """Calculate median cycle time (hours) considering working hours and weekends."""
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        case_start = df.groupby(case_id_col)[start_time_col].min().rename("Case_Start")
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename("Case_End")
        df_cycle = pd.merge(case_start, case_end, on=case_id_col)

        df_cycle["Working_Seconds"] = df_cycle.apply(
            lambda r: calculate_net_working_time(
                r["Case_Start"], r["Case_End"], office_start_hour, office_end_hour
            ),
            axis=1,
        )
        df_cycle["Cycle_Hours"] = df_cycle["Working_Seconds"] / 3600

        median_hours = round(df_cycle["Cycle_Hours"].median(), 2)
        return json.dumps(
            {"Median_Cycle_Time_Hours": median_hours, "Total_Cases": len(df_cycle)},
            indent=4,
        )

    except Exception as e:
        return json.dumps({"Error": f"Failed to calculate median cycle time: {e}"}, indent=4)
    

def get_minimum_cycle_time_hours(
    event_log_data,
    case_id_col,
    activity_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour
):
    """
    Calculate the minimum cycle time (hours) among cases that reached the expected final activity.
    Uses same logic as median function + adds final activity filtering.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)

        # --- Normalize column names to avoid mismatch ---
        # df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]
        # case_id_col = case_id_col.strip().lower().replace(" ", "_")
        # activity_col = activity_col.strip().lower().replace(" ", "_")
        # start_time_col = start_time_col.strip().lower().replace(" ", "_")
        # complete_time_col = complete_time_col.strip().lower().replace(" ", "_")

        # --- Validate required columns ---
        required_cols = [case_id_col, activity_col, start_time_col, complete_time_col]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return json.dumps({
                "Error": f"Missing required columns: {missing}",
                "Available_Columns": list(df.columns)
            }, indent=4)

        # --- Parse timestamps ---
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True, errors="coerce")
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True, errors="coerce")

        df = df.dropna(subset=[case_id_col, activity_col, start_time_col, complete_time_col])

        # --- 1️⃣ Identify the expected final activity (most common last step) ---
        last_acts = (
            df.sort_values(by=complete_time_col)
            .groupby(case_id_col)
            .last()
            .reset_index()
        )
        expected_final_activity = last_acts[activity_col].mode().iloc[0]

        # --- 2️⃣ Filter only cases that actually reached that final activity ---
        valid_cases = last_acts[last_acts[activity_col] == expected_final_activity][case_id_col]
        df = df[df[case_id_col].isin(valid_cases)]

        if df.empty:
            return json.dumps({
                "Minimum_Cycle_Time_Hours": 0.0,
                "Case_ID_With_Min_Cycle_Time": None,
                "Total_Completed_Cases": 0,
                "Expected_Final_Activity": expected_final_activity,
                "Warning": "No completed cases found reaching expected final activity."
            }, indent=4)

        # --- 3️⃣ Same as your working median logic ---
        case_start = df.groupby(case_id_col)[start_time_col].min().rename("Case_Start")
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename("Case_End")
        df_cycle = pd.merge(case_start, case_end, on=case_id_col)

        # --- 4️⃣ Calculate working time (respecting office hours & weekends) ---
        df_cycle["Working_Seconds"] = df_cycle.apply(
            lambda r: calculate_net_working_time(
                r["Case_Start"], r["Case_End"], office_start_hour, office_end_hour
            ),
            axis=1,
        )
        df_cycle["Cycle_Hours"] = df_cycle["Working_Seconds"] / 3600
        df_cycle = df_cycle[df_cycle["Cycle_Hours"] > 0]

        if df_cycle.empty:
            return json.dumps({
                "Minimum_Cycle_Time_Hours": 0.0,
                "Case_ID_With_Min_Cycle_Time": None,
                "Total_Completed_Cases": 0,
                "Expected_Final_Activity": expected_final_activity
            }, indent=4)

        # --- 5️⃣ Minimum cycle time among completed cases ---
        min_case = df_cycle.loc[df_cycle["Cycle_Hours"].idxmin()]

        return json.dumps({
            "Minimum_Cycle_Time_Hours": round(min_case["Cycle_Hours"], 2),
            "Case_ID_With_Min_Cycle_Time": str(min_case.name),
            "Total_Completed_Cases": int(len(df_cycle)),
            "Expected_Final_Activity": expected_final_activity
        }, indent=4)

    except Exception as e:
        return json.dumps({
            "Error": f"An error occurred during minimum cycle time calculation: {e}"
        }, indent=4)

# def calculate_all_cycle_time_metrics(
#     event_log_data,              
#     case_id_col,                 
#     start_time_col,              
#     complete_time_col,           
#     office_start_hour=6,         
#     office_end_hour=18,          
#     time_unit='hours',
#     start_date_filter=None,      
#     end_date_filter=None         
# ):
    
#     if not event_log_data:
#         return json.dumps({"Error": "Event log data is empty."}, indent=4)
        
#     try:        
#         df = pd.DataFrame(event_log_data)
#         required_cols = [case_id_col, start_time_col, complete_time_col]
#         if not all(col in df.columns for col in required_cols):
#              missing = [col for col in required_cols if col not in df.columns]
#              return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)
#     except Exception as e:
#         return json.dumps({"Error": f"An error occurred during DataFrame creation: {e}"}, indent=4)

#     df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
#     df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

#     if start_date_filter or end_date_filter:
#         try:
#             start_filter_dt = pd.to_datetime(start_date_filter, utc=True) if start_date_filter else pd.NaT
#             end_filter_dt = pd.to_datetime(end_date_filter, utc=True) if end_date_filter else pd.NaT

#             if pd.notna(start_filter_dt):
#                 df = df[df[start_time_col] >= start_filter_dt].copy()
            
#             if pd.notna(end_filter_dt):
#                 df = df[df[complete_time_col] < end_filter_dt].copy()

#         except Exception as e:
#             print(f"Warning: Failed to parse date filter. Analysis proceeded without filtering. Error: {e}")
            
#     if df.empty:
#         return json.dumps({"Warning": "No data available for analysis after applying date filters."}, indent=4)

#     case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
#     case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
#     df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()

#     df_cycle_times['Adjusted_Cycle_Time_Seconds'] = df_cycle_times.apply(
#         lambda row: calculate_net_working_time(
#             row['Case_Start'], 
#             row['Case_End'], 
#             office_start_hour, 
#             office_end_hour
#         ), 
#         axis=1
#     )
   
#     unit_conversion = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'days': 86400}
#     divisor = unit_conversion.get(time_unit.lower(), 3600)
    
#     df_cycle_times['Adjusted_Cycle_Time'] = (
#         df_cycle_times['Adjusted_Cycle_Time_Seconds'] / divisor
#     )

#     cycle_times = df_cycle_times['Adjusted_Cycle_Time'].values
#     num_cases = len(cycle_times)
    
#     if num_cases == 0:
#         return json.dumps({"Error": "No cases found after grouping."}, indent=4)

#     mean_time = np.mean(cycle_times)
#     variance_time = np.var(cycle_times, ddof=0)
#     std_dev_time = np.std(cycle_times, ddof=0)

#     metrics = {
#         "Total_Cases": num_cases,
#         f"Average (Mean) Cycle Time ({time_unit})": round(mean_time, 2),
#         f"Median Cycle Time ({time_unit})": round(np.median(cycle_times), 2),
#         f"Minimum Cycle Time ({time_unit})": round(np.min(cycle_times), 2),
#         f"Maximum Cycle Time ({time_unit})": round(np.max(cycle_times), 2),
#         f"Variance ({time_unit}^2)": round(variance_time, 2),
#         f"Standard Deviation ({time_unit})": round(std_dev_time, 2),
#     }

#     return json.dumps(metrics, indent=4)


def get_cycle_time_over_period(
    event_log_data,
    case_id_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour,
    aggregation_level='month', # New: 'week', 'month', or 'all'
    start_date_filter=None,    # New: Filter data starting from this date (inclusive)
    end_date_filter=None       # New: Filter data ending before this date (exclusive)
):
     
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)


        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()
        

        df_cycle_times['Adjusted_Cycle_Time_Seconds'] = df_cycle_times.apply(
            lambda row: calculate_net_working_time(
                row['Case_Start'], 
                row['Case_End'], 
                office_start_hour, 
                office_end_hour
            ), 
            axis=1
        )        
        
        df_cycle_times['Cycle_Time_Days'] = df_cycle_times['Adjusted_Cycle_Time_Seconds'] / 86400.0


        if start_date_filter:
            start_filter_dt = pd.to_datetime(start_date_filter, utc=True)
            df_cycle_times = df_cycle_times[df_cycle_times['Case_Start'] >= start_filter_dt].copy()
        
        if end_date_filter:
            end_filter_dt = pd.to_datetime(end_date_filter, utc=True)
            df_cycle_times = df_cycle_times[df_cycle_times['Case_End'] < end_filter_dt].copy()

        if df_cycle_times.empty:
            return json.dumps({"Warning": "No data available for analysis after filtering."}, indent=4)



        agg_level = aggregation_level.lower()
        
        if agg_level == 'week':

            df_cycle_times['Group_Period'] = df_cycle_times['Case_End'].dt.to_period('W').astype(str)
            period_name = 'week'
        elif agg_level == 'month':

            df_cycle_times['Group_Period'] = df_cycle_times['Case_End'].dt.to_period('M').astype(str)
            period_name = 'month'
        elif agg_level == 'all':

            df_cycle_times['Group_Period'] = 'All Time Summary'
            period_name = 'summary_period'
        else:
            return json.dumps({"Error": f"Invalid aggregation_level: '{aggregation_level}'. Must be 'week', 'month', or 'all'."}, indent=4)


        period_metrics = df_cycle_times.groupby('Group_Period')['Cycle_Time_Days'].agg(
            Average_Cycle_Time=('mean'),
            Median_Cycle_Time=('median'),
            Total_Cases=('size')
        ).reset_index()


        period_metrics['Average_Cycle_Time'] = period_metrics['Average_Cycle_Time'].round(2)
        period_metrics['Median_Cycle_Time'] = period_metrics['Median_Cycle_Time'].round(2)

        data_records = period_metrics.rename(columns={
            'Group_Period': period_name, 
            'Average_Cycle_Time': 'average_cycle_time_days',
            'Median_Cycle_Time': 'median_cycle_time_days',
            'Total_Cases': 'total_cases'
        }).to_dict('records')
        
        return json.dumps(data_records, indent=4)
    
    except Exception as e:
        return json.dumps({"Error": f"An error occurred during data processing: {e}"}, indent=4)
    


def calculate_total_cases(event_log_data, case_id_col, start_time_col, complete_time_col, start_date_filter=None, end_date_filter=None):
    
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
        
    try:
        df = pd.DataFrame(event_log_data)
        

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cases = case_end.reset_index()

        filtered_df = df_cases.copy()
        
        if start_date_filter:
            start_filter_dt = pd.to_datetime(start_date_filter, utc=True)
            filtered_df = filtered_df[filtered_df['Case_End'] >= start_filter_dt].copy()
        
        if end_date_filter:
            end_filter_dt = pd.to_datetime(end_date_filter, utc=True)         
            filtered_df = filtered_df[filtered_df['Case_End'] < end_filter_dt].copy()

      
        num_cases = filtered_df[case_id_col].nunique()

        result = {
            "Total_Unique_Cases": num_cases
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during case counting and filtering: {e}"}, indent=4)


def get_average_idle_time_hours(
    event_log_data,
    case_id_col,
    activity_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour
):
    """
    Calculate the average idle time (in hours) per case,
    considering working hours and excluding weekends.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
       

        # --- Parse timestamps ---
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True, errors="coerce")
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True, errors="coerce")
        df = df.dropna(subset=[case_id_col, start_time_col, complete_time_col])

        # --- Step 1️⃣: Compute total working duration per activity ---
        df["Activity_Working_Seconds"] = df.apply(
            lambda r: calculate_net_working_time(
                r[start_time_col], r[complete_time_col],
                office_start_hour, office_end_hour
            ),
            axis=1
        )

        # --- Step 2️⃣: Compute total case working duration (start → end) ---
        case_start = df.groupby(case_id_col)[start_time_col].min().rename("Case_Start")
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename("Case_End")
        df_case = pd.merge(case_start, case_end, on=case_id_col)

        df_case["Case_Working_Seconds"] = df_case.apply(
            lambda r: calculate_net_working_time(
                r["Case_Start"], r["Case_End"],
                office_start_hour, office_end_hour
            ),
            axis=1
        )

        # --- Step 3️⃣: Sum of all activities per case ---
        df_activity_sum = df.groupby(case_id_col)["Activity_Working_Seconds"].sum().rename("Total_Activity_Working_Seconds")

        # --- Step 4️⃣: Merge to calculate idle time ---
        df_case = pd.merge(df_case, df_activity_sum, on=case_id_col, how="left")

        df_case["Idle_Seconds"] = df_case["Case_Working_Seconds"] - df_case["Total_Activity_Working_Seconds"]
        df_case["Idle_Hours"] = df_case["Idle_Seconds"] / 3600
        df_case["Idle_Hours"] = df_case["Idle_Hours"].apply(lambda x: max(x, 0))  # avoid negatives

        # --- Step 5️⃣: Calculate average idle time per case ---
        avg_idle_hours = round(df_case["Idle_Hours"].mean(), 2)

        return json.dumps({
            "Average_Idle_Time_Hours": avg_idle_hours,
            "Total_Cases": int(len(df_case))
        }, indent=4)

    except Exception as e:
        return json.dumps({
            "Error": f"Failed to calculate average idle time per case: {e}"
        }, indent=4)
    


def calculate_average_idle_time_metrics(
    event_log_data,
    case_id_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour
):
    """
    Calculate the average idle time (in hours) per case and the average idle ratio (%),
    considering working hours and excluding weekends.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)

        # --- Validate columns ---
        required_cols = [case_id_col, start_time_col, complete_time_col]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        # --- Convert timestamps ---
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True, errors="coerce")
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True, errors="coerce")
        df = df.dropna(subset=[case_id_col, start_time_col, complete_time_col])

        # --- Per-case start and end times ---
        case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle = pd.merge(case_start, case_end, on=case_id_col).reset_index()

        # --- Total (calendar) time per case ---
        df_cycle['Total_Cycle_Seconds'] = (
            df_cycle['Case_End'] - df_cycle['Case_Start']
        ).dt.total_seconds()

        # --- Working time per case (within office hours, excluding weekends) ---
        df_cycle['Working_Seconds'] = df_cycle.apply(
            lambda row: calculate_net_working_time(
                row['Case_Start'], row['Case_End'], office_start_hour, office_end_hour
            ),
            axis=1
        )

        # --- Idle time per case ---
        df_cycle['Idle_Seconds'] = df_cycle['Total_Cycle_Seconds'] - df_cycle['Working_Seconds']
        df_cycle['Idle_Seconds'] = df_cycle['Idle_Seconds'].clip(lower=0)

        # --- Idle ratio per case ---
        df_cycle['Idle_Ratio'] = (
            df_cycle['Idle_Seconds'] / df_cycle['Total_Cycle_Seconds']
        ).fillna(0)

        # --- Aggregate (average) metrics ---
        avg_idle_hours = round(df_cycle['Idle_Seconds'].mean() / 3600, 2)
        avg_idle_ratio = round(df_cycle['Idle_Ratio'].mean() * 100, 2)

        result = {
            "Average_Idle_Time_Hours_Per_Case": avg_idle_hours,
            "Average_Idle_Time_Ratio_Percentage": avg_idle_ratio,
            "Total_Cases": int(len(df_cycle))
        }

        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({
            "Error": f"An error occurred during average idle time calculation: {e}"
        }, indent=4)
    


def calculate_loop_metrics(event_log_data, case_id_col, activity_col):
    """
    Calculate loop metrics for process mining.
    Includes per-activity loop occurrence counts.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)

        # --- Validate required columns ---
        required_cols = [case_id_col, activity_col]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return json.dumps(
                {"Error": f"Missing required columns in data: {missing}"}, indent=4
            )

        total_steps = len(df)

        # --- Case-level metrics ---
        case_metrics = df.groupby(case_id_col).agg(
            Total_Events_Per_Case=(activity_col, "count"),
            Unique_Activities_Per_Case=(activity_col, "nunique"),
        ).reset_index()

        case_metrics["Loops_Per_Case"] = (
            case_metrics["Total_Events_Per_Case"]
            - case_metrics["Unique_Activities_Per_Case"]
        )

        total_loops = int(case_metrics["Loops_Per_Case"].sum())
        loop_ratio = (total_loops / total_steps) if total_steps > 0 else 0.0

        # --- NEW: Calculate per-activity loop frequency ---
        df_activity_counts = (
            df.groupby([case_id_col, activity_col])
            .size()
            .reset_index(name="Activity_Count_Per_Case")
        )

        # Filter where an activity appears more than once per case → a loop
        df_loops = df_activity_counts[df_activity_counts["Activity_Count_Per_Case"] > 1]

        # Count how many cases each activity was repeated in
        loop_counts_by_activity = (
            df_loops.groupby(activity_col)
            .size()
            .reset_index(name="Loop_Occurrences")
            .sort_values(by="Loop_Occurrences", ascending=False)
            .reset_index(drop=True)
        )

        # Convert to dictionary form for clean JSON output
        loop_activity_dict = loop_counts_by_activity.set_index(activity_col)[
            "Loop_Occurrences"
        ].to_dict()

        # --- Build Final Result ---
        result = {
            "Total_Loops": total_loops,
            "Total_Process_Steps": int(total_steps),
            "Loops_Ratio_Percentage": round(loop_ratio * 100, 2),
            "Loop_Activity_Details": loop_activity_dict,  # 🔥 New addition
        }

        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps(
            {"Error": f"An error occurred during loop calculation: {e}"}, indent=4
        )



def calculate_bottleneck_metrics(
    event_log_data,
    case_id_col,
    activity_col,
    start_time_col,
    complete_time_col
):
    """
    Calculate bottleneck metrics with occurrence count.
    Adds 'Bottleneck_Occurrence_Count' for how many times
    the main bottleneck activity exceeded its average time.
    """

    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        # --- Validate required columns ---
        required_cols = [case_id_col, activity_col, start_time_col, complete_time_col]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        # --- Convert timestamps ---
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        # --- Calculate processing times ---
        df['Processing_Time_Seconds'] = (
            df[complete_time_col] - df[start_time_col]
        ).dt.total_seconds()
        
        # --- Average processing time per activity ---
        avg_processing_time_summary = (
            df.groupby(activity_col)['Processing_Time_Seconds']
            .mean()
            .reset_index()
            .rename(columns={'Processing_Time_Seconds': 'Average_Time_Seconds'})
        )
        avg_processing_time_summary['Average_Time_Hours'] = (
            avg_processing_time_summary['Average_Time_Seconds'] / 3600
        ).round(2)

        activity_avg_times = avg_processing_time_summary.set_index(activity_col)['Average_Time_Hours'].to_dict()

        # --- Merge back and compute deviation ---
        df_analysis = pd.merge(
            df,
            avg_processing_time_summary[[activity_col, 'Average_Time_Seconds']],
            on=activity_col,
            how='left'
        )

        df_analysis['Deviation_Seconds'] = (
            df_analysis['Processing_Time_Seconds'] - df_analysis['Average_Time_Seconds']
        )

        df_analysis['Excess_Time_Seconds'] = df_analysis['Deviation_Seconds'].apply(lambda x: max(0, x))

        total_time_lost_seconds = df_analysis['Excess_Time_Seconds'].sum()

        bottleneck_metrics = {
            "Bottleneck_Activity": "N/A",
            "Bottleneck_Case_ID": "N/A",
            "Max_Excess_Time_Hours": 0.0,
            "Total_Time_Lost_Hours": 0.0,
            "Bottleneck_Ratio_Percentage": 0.0,
            "Bottleneck_Occurrence_Count": 0
        }

        if total_time_lost_seconds > 0:
            # --- Find the single largest bottleneck event ---
            max_bottleneck_row = df_analysis.loc[df_analysis['Excess_Time_Seconds'].idxmax()]

            # --- Calculate total cycle time across all cases ---
            case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
            case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
            df_case_duration = pd.merge(case_start, case_end, on=case_id_col).reset_index()

            df_case_duration['Total_Cycle_Time_Seconds'] = (
                df_case_duration['Case_End'] - df_case_duration['Case_Start']
            ).dt.total_seconds()
            
            total_process_wall_time_seconds = df_case_duration['Total_Cycle_Time_Seconds'].sum()

            bottleneck_ratio = (
                total_time_lost_seconds / total_process_wall_time_seconds
            ) if total_process_wall_time_seconds > 0 else 0.0

            # --- NEW: Count how many times this activity exceeded its average ---
            main_bottleneck_activity = max_bottleneck_row[activity_col]
            bottleneck_occurrence_count = df_analysis[
                (df_analysis[activity_col] == main_bottleneck_activity) &
                (df_analysis['Deviation_Seconds'] > 0)
            ].shape[0]

            # --- Store results ---
            bottleneck_metrics = {
                "Bottleneck_Activity": main_bottleneck_activity,
                "Bottleneck_Case_ID": max_bottleneck_row[case_id_col],
                "Max_Excess_Time_Hours": round(max_bottleneck_row['Excess_Time_Seconds'] / 3600, 2),
                "Total_Time_Lost_Hours": round(total_time_lost_seconds / 3600, 2),
                "Bottleneck_Ratio_Percentage": round(bottleneck_ratio * 100, 2),
                "Bottleneck_Occurrence_Count": int(bottleneck_occurrence_count)
            }

        # --- Final result ---
        result = {
            "Activity_Average_Processing_Time_Hours": activity_avg_times,
            "Largest_Bottleneck_Metrics": bottleneck_metrics,
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps(
            {"Error": f"An error occurred during bottleneck calculation: {e}"},
            indent=4
        )
    
def calculate_largest_bottlenecks(
    event_log_data,
    case_id_col,
    activity_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour,
    top_n=5
):
    """
    Identify the largest bottlenecks based on average activity duration,
    considering office hours and excluding weekends.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        # --- Validate columns ---
        required_cols = [case_id_col, activity_col, start_time_col, complete_time_col]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)
        
        # --- Parse timestamps ---
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True, errors='coerce')
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True, errors='coerce')
        df = df.dropna(subset=[activity_col, start_time_col, complete_time_col])

        # --- Compute working duration per event ---
        df['Working_Seconds'] = df.apply(
            lambda r: calculate_net_working_time(
                r[start_time_col], r[complete_time_col],
                office_start_hour, office_end_hour
            ),
            axis=1
        )

        df['Working_Hours'] = df['Working_Seconds'] / 3600

        # --- Compute average and total duration per activity ---
        df_activity = (
            df.groupby(activity_col)['Working_Hours']
            .agg(['mean', 'count'])
            .reset_index()
            .rename(columns={'mean': 'Average_Duration_Hours', 'count': 'Total_Occurrences'})
        )

        # --- Compute overall average for threshold ---
        overall_avg = df_activity['Average_Duration_Hours'].mean()

        # --- Identify bottlenecks: those above the overall average ---
        df_activity['Is_Bottleneck'] = df_activity['Average_Duration_Hours'] > overall_avg

        # --- Sort and take top N largest bottlenecks ---
        largest_bottlenecks = (
            df_activity.sort_values(by='Average_Duration_Hours', ascending=False)
            .head(top_n)
            .reset_index(drop=True)
        )

        # --- Prepare JSON output ---
        result = {
            "KPI_Name": "Largest Bottlenecks",
            "Overall_Average_Activity_Duration_Hours": round(overall_avg, 2),
            "Top_Bottlenecks": [
                {
                    "Activity": row[activity_col],
                    "Average_Duration_Hours": round(row["Average_Duration_Hours"], 2),
                    "Total_Occurrences": int(row["Total_Occurrences"]),
                    "Is_Bottleneck": bool(row["Is_Bottleneck"])
                }
                for _, row in largest_bottlenecks.iterrows()
            ]
        }

        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({
            "Error": f"An error occurred during bottleneck analysis: {e}"
        }, indent=4)
    



def calculate_steps_per_case_metrics(event_log_data, case_id_col):
   
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        if case_id_col not in df.columns:
             return json.dumps({"Error": f"Missing required column in data: {case_id_col}"}, indent=4)

        steps_per_case = df.groupby(case_id_col).size().rename('Steps_Count')
        
        if steps_per_case.empty:
            return json.dumps({
                "Average_Steps_Per_Case": 0.0,
                "Median_Steps_Per_Case": 0.0
            }, indent=4)

        average_steps = steps_per_case.mean()

        median_steps = steps_per_case.median()

        result = {
            "Average_Steps_Per_Case": round(average_steps, 2),
            "Median_Steps_Per_Case": round(median_steps, 2),
            "Total_Cases": int(steps_per_case.count()),
            "Total_Steps": int(steps_per_case.sum())
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during steps per case calculation: {e}"}, indent=4)
    



def calculate_dropout_rate(
    event_log_data,
    case_id_col,
    activity_col,
    complete_time_col
):
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, complete_time_col]
        if not all(col in df.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df.columns]
            return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        # Sort events to get the latest per case
        df_sorted = df.sort_values(by=complete_time_col, ascending=False)
        last_events = df_sorted.groupby(case_id_col).first().reset_index()

        total_cases = last_events[case_id_col].nunique()

        if total_cases == 0:
            return json.dumps({
                "Dropout_Rate_Percentage": 0.0,
                "Number_of_Dropout_Cases": 0,
                "Total_Cases": 0,
                "Expected_Final_Activity_Derived": "N/A",
                "Dropout_Activity_Counts": {}
            }, indent=4)

        # Determine the most frequent final activity (expected)
        activity_counts = last_events[activity_col].value_counts()
        most_common_final_activity = activity_counts.index[0]
        cases_ending_with_expected = int(activity_counts.iloc[0])

        # Identify cases that dropped out before reaching expected final activity
        dropout_cases = last_events[
            last_events[activity_col] != most_common_final_activity
        ]
        num_dropout_cases = len(dropout_cases)

        # 🔹 NEW: Count each type of dropout activity
        dropout_activity_counts = (
            dropout_cases[activity_col].value_counts().to_dict()
            if num_dropout_cases > 0 else {}
        )

        dropout_rate = (num_dropout_cases / total_cases)

        result = {
            "Dropout_Rate_Percentage": round(dropout_rate * 100, 2),
            "Number_of_Dropout_Cases": int(num_dropout_cases),
            "Total_Cases": int(total_cases),
            "Expected_Final_Activity_Derived": most_common_final_activity,
            "Cases_Ending_With_Expected_Activity": cases_ending_with_expected,
            "Dropout_Activity_Counts": dropout_activity_counts
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({
            "Error": f"An error occurred during dropout rate calculation: {e}"
        }, indent=4)




def calculate_average_activity_duration(
    event_log_data,
    activity_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour
):
    """
    Calculates the average activity duration (in hours) for each activity,
    considering working hours and excluding weekends.
    Returns data ready for visualization (e.g., bar chart).
    """
    import pandas as pd, json

    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)

        # Validate required columns
        required_cols = [activity_col, start_time_col, complete_time_col]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return json.dumps({"Error": f"Missing required columns: {missing}"}, indent=4)

        # Parse timestamps
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True, errors='coerce')
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True, errors='coerce')

        # Drop invalid rows
        df = df.dropna(subset=[activity_col, start_time_col, complete_time_col])

        # Calculate working duration in seconds for each event
        df["Working_Seconds"] = df.apply(
            lambda row: calculate_net_working_time(
                row[start_time_col],
                row[complete_time_col],
                office_start_hour,
                office_end_hour
            ),
            axis=1
        )

        # Convert to hours
        df["Working_Hours"] = df["Working_Seconds"] / 3600.0

        # Average duration per activity
        activity_avg = (
            df.groupby(activity_col)["Working_Hours"]
            .mean()
            .round(2)
            .reset_index()
            .rename(columns={"Working_Hours": "Average_Activity_Duration_Hours"})
        )

        # Sort longest → shortest
        activity_avg = activity_avg.sort_values(by="Average_Activity_Duration_Hours", ascending=False)

        # For chart output
        bar_chart_data = [
            {
                "activity": row[activity_col],
                "average_duration_hours": float(row["Average_Activity_Duration_Hours"])
            }
            for _, row in activity_avg.iterrows()
        ]

        result = {
            "KPI_Name": "Average Activity Duration",
            "Total_Activities": int(activity_avg.shape[0]),
            "Average_Activity_Durations": bar_chart_data
        }

        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during average activity duration calculation: {e}"}, indent=4)
    

def calculate_process_variants(
    event_log_data,
    case_id_col,
    activity_col,
    complete_time_col
):

    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)

        required_cols = [case_id_col, activity_col, complete_time_col] 
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])

        case_traces = df_sorted.groupby(case_id_col)[activity_col].apply(list).reset_index()

        case_traces['Variant'] = case_traces[activity_col].apply(lambda x: ' -> '.join(x))

        variant_counts = case_traces['Variant'].value_counts()

        total_unique_variants = len(variant_counts)
        total_cases = len(case_traces)
        
        most_frequent_variant = "N/A"
        most_frequent_count = 0
        
        if not variant_counts.empty:
            most_frequent_variant = variant_counts.index[0]
            most_frequent_count = int(variant_counts.iloc[0])
        
        most_frequent_percentage = (most_frequent_count / total_cases) * 100 if total_cases > 0 else 0.0

        result = {
            "Total_Unique_Process_Variants": int(total_unique_variants),
            "Total_Cases_Analyzed": int(total_cases),
            "Most_Frequent_Variant": most_frequent_variant,
            "Most_Frequent_Variant_Count": most_frequent_count,
            "Most_Frequent_Variant_Percentage": round(most_frequent_percentage, 2)
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during process variant calculation: {e}"}, indent=4)
    


def calculate_top_variants(
    event_log_data,
    case_id_col,
    activity_col,
    complete_time_col,
    top_n=10 # Default to Top 5
):
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, complete_time_col] 
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])

        case_traces = df_sorted.groupby(case_id_col)[activity_col].apply(list).reset_index()

        case_traces['Variant'] = case_traces[activity_col].apply(lambda x: ' -> '.join(x))

        variant_counts = case_traces['Variant'].value_counts()
        total_cases = len(case_traces)

        top_variants_data = []

        for variant, count in variant_counts.head(top_n).items():
            percentage = (count / total_cases) * 100 if total_cases > 0 else 0.0
            
            top_variants_data.append({
                "Variant_Trace": variant,
                "Count": int(count),
                "Percentage": round(percentage, 2)
            })

        result = {
            "Total_Unique_Process_Variants": len(variant_counts),
            "Total_Cases_Analyzed": int(total_cases),
            "Top_Process_Variants": top_variants_data
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during process variant calculation: {e}"}, indent=4)
    



def calculate_first_pass_rate(
    event_log_data,
    case_id_col,
    activity_col
):
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        case_metrics = df.groupby(case_id_col).agg(
            Total_Events_Per_Case=(case_id_col, 'count'),
            Unique_Activities_Per_Case=(activity_col, 'nunique')
        ).reset_index()

        case_metrics['Is_First_Pass'] = (
            case_metrics['Total_Events_Per_Case'] == case_metrics['Unique_Activities_Per_Case']
        )

        total_cases = len(case_metrics)
        first_pass_cases = case_metrics['Is_First_Pass'].sum()

        first_pass_rate = (first_pass_cases / total_cases) * 100 if total_cases > 0 else 0.0

        result = {
            "Total_Cases_Analyzed": int(total_cases),
            "First_Pass_Cases": int(first_pass_cases),
            "Rework_Cases": int(total_cases - first_pass_cases),
            "First_Pass_Rate_Percentage": round(first_pass_rate, 2),
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during First Pass Rate calculation: {e}"}, indent=4)




def calculate_longest_waiting_time_step(
    event_log_data,
    case_id_col,
    activity_col,
    start_time_col,
    complete_time_col
):
 
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, start_time_col, complete_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        df_sorted = df.sort_values(by=[case_id_col, complete_time_col]).reset_index(drop=True)

        df_sorted['Next_Activity'] = df_sorted.groupby(case_id_col)[activity_col].shift(-1)
        df_sorted['Next_Start_Time'] = df_sorted.groupby(case_id_col)[start_time_col].shift(-1)

        df_transitions = df_sorted.dropna(subset=['Next_Activity']).copy()

        df_transitions['Waiting_Time_Seconds'] = (
            df_transitions['Next_Start_Time'] - df_transitions[complete_time_col]
        ).dt.total_seconds()

        df_transitions = df_transitions[df_transitions['Waiting_Time_Seconds'] >= 0]

        transition_metrics = df_transitions.groupby([activity_col, 'Next_Activity'])['Waiting_Time_Seconds'].agg(
            Average_Waiting_Time_Seconds='mean',
            Transition_Count='count'
        ).reset_index()
        
        if transition_metrics.empty:
            return json.dumps({
                "Longest_Waiting_Time_Step": "N/A",
                "Max_Average_Waiting_Time_Hours": 0.0,
                "Total_Transitions_Analyzed": 0
            }, indent=4)

        longest_wait_step = transition_metrics.loc[
            transition_metrics['Average_Waiting_Time_Seconds'].idxmax()
        ]
        
        max_avg_wait_seconds = longest_wait_step['Average_Waiting_Time_Seconds']
        
        result = {
            "Longest_Waiting_Time_Step": f"{longest_wait_step[activity_col]} -> {longest_wait_step['Next_Activity']}",
            "Max_Average_Waiting_Time_Hours": round(max_avg_wait_seconds / 3600, 2),
            "Max_Average_Waiting_Time_Seconds": round(max_avg_wait_seconds, 2),
            "Total_Transitions_Analyzed": int(len(df_transitions))
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during waiting time step calculation: {e}"}, indent=4)



def calculate_variant_complexity_index(
    event_log_data,
    case_id_col,
    activity_col,
    complete_time_col
):
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, complete_time_col] 
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])

        case_traces = df_sorted.groupby(case_id_col)[activity_col].apply(list).reset_index()

        case_traces['Variant'] = case_traces[activity_col].apply(lambda x: ' -> '.join(x))

        variant_counts = case_traces['Variant'].value_counts()

        total_unique_variants = len(variant_counts)
        total_cases = len(case_traces)

        variant_complexity_index = (
            total_unique_variants / total_cases
        ) if total_cases > 0 else 0.0

        result = {
            "Total_Cases_Analyzed": int(total_cases),
            "Total_Unique_Process_Variants": int(total_unique_variants),
            "Variant_Complexity_Index": round(variant_complexity_index, 4), 
            "Variant_Complexity_Index_Percentage": round(variant_complexity_index * 100, 2)
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during VCI calculation: {e}"}, indent=4)



def calculate_variant_change_over_time(
    event_log_data,
    case_id_col,
    activity_col,
    complete_time_col,
    time_period='W' # 'D' for Daily, 'W' for Weekly, 'M' for Monthly
):
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    if time_period.upper() not in ['D', 'W', 'M']:
        return json.dumps({"Error": f"Invalid time_period: {time_period}. Must be 'D', 'W', or 'M'."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, complete_time_col] 
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])
        case_traces = df_sorted.groupby(case_id_col).agg(
            Variant=(activity_col, lambda x: ' -> '.join(x)),
            Case_End_Time=(complete_time_col, 'max') 
        ).reset_index()

        case_traces['Time_Period'] = case_traces['Case_End_Time'].dt.to_period(time_period.upper())

        time_trend = case_traces.groupby('Time_Period').agg(
            Unique_Variant_Count=('Variant', 'nunique'),
            Total_Cases_Completed=('case_id', 'count')
        ).reset_index()

        time_trend['Variant_Complexity_Index'] = (
            time_trend['Unique_Variant_Count'] / time_trend['Total_Cases_Completed']
        )

        time_trend['Time_Period_Label'] = time_trend['Time_Period'].astype(str)
 
        time_trend_list = time_trend[[
            'Time_Period_Label', 
            'Unique_Variant_Count', 
            'Total_Cases_Completed', 
            'Variant_Complexity_Index'
        ]].to_dict('records')

        for item in time_trend_list:
            item['Variant_Complexity_Index'] = round(item['Variant_Complexity_Index'], 4)

        result = {
            "Time_Aggregation_Level": time_period.upper(),
            "Variant_Change_Trend": time_trend_list
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during VCI over time calculation: {e}"}, indent=4)
    


def calculate_cases_following_top_variant(
    event_log_data,
    case_id_col,
    activity_col,
    complete_time_col
):
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, complete_time_col] 
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])

        case_traces = df_sorted.groupby(case_id_col)[activity_col].apply(list).reset_index()

        case_traces['Variant'] = case_traces[activity_col].apply(lambda x: ' -> '.join(x))

        variant_counts = case_traces['Variant'].value_counts()

        total_cases = len(case_traces)
        most_frequent_count = 0
        most_frequent_variant = "N/A"
        
        if not variant_counts.empty:
            most_frequent_count = int(variant_counts.iloc[0])
            most_frequent_variant = variant_counts.index[0]

        top_variant_percentage = (most_frequent_count / total_cases) * 100 if total_cases > 0 else 0.0

        result = {
            "Total_Cases_Analyzed": int(total_cases),
            "Top_Variant_Trace": most_frequent_variant,
            "Top_Variant_Count": most_frequent_count,
            "Cases_Following_Top_Variant_Percentage": round(top_variant_percentage, 2)
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during top variant conformance calculation: {e}"}, indent=4)



def calculate_max_steps_in_a_case(event_log_data, case_id_col):
   
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        if case_id_col not in df.columns:
             return json.dumps({"Error": f"Missing required column in data: {case_id_col}"}, indent=4)

        steps_per_case = df.groupby(case_id_col).size().rename('Steps_Count')
        
        if steps_per_case.empty:
            return json.dumps({
                "Max_Steps_Count": 0,
                "Case_ID_With_Max_Steps": "N/A"
            }, indent=4)

        max_steps = int(steps_per_case.max())

        case_id_with_max_steps = steps_per_case[steps_per_case == max_steps].index.tolist()

        result = {
            "Max_Steps_Count": max_steps,
            "Case_ID_With_Max_Steps": case_id_with_max_steps[0] if case_id_with_max_steps else "N/A",
            "Cases_Tied_for_Max": len(case_id_with_max_steps)
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during max steps calculation: {e}"}, indent=4)


def seconds_to_dhms(seconds):

    if seconds < 0:
        sign = "-"
        seconds = abs(seconds)
    else:
        sign = ""

    days = math.floor(seconds / (3600 * 24))
    seconds %= (3600 * 24)
    hours = math.floor(seconds / 3600)
    seconds %= 3600
    minutes = math.floor(seconds / 60)
    seconds %= 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts: 
        parts.append(f"{round(seconds, 2)}s")

    return sign + " ".join(parts)


def calculate_average_time_saved_potential(
    event_log_data,
    case_id_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour
):
    """
    Calculate the Average Time Saved Potential KPI.

    This compares each case duration against the fastest case ("Happy Path"),
    within a +10% variance margin, considering office hours and excluding weekends.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        required_cols = [case_id_col, start_time_col, complete_time_col]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return json.dumps({"Error": f"Missing required columns: {missing}"}, indent=4)

        # --- Parse timestamps ---
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True, errors="coerce")
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True, errors="coerce")
        df = df.dropna(subset=[case_id_col, start_time_col, complete_time_col])

        # --- Compute Case Durations (in working hours) ---
        case_start = df.groupby(case_id_col)[start_time_col].min().rename("Case_Start")
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename("Case_End")
        df_cycle = pd.merge(case_start, case_end, on=case_id_col)

        df_cycle["Working_Seconds"] = df_cycle.apply(
            lambda r: calculate_net_working_time(
                r["Case_Start"], r["Case_End"], office_start_hour, office_end_hour
            ),
            axis=1
        )
        df_cycle["Cycle_Hours"] = df_cycle["Working_Seconds"] / 3600

        # --- Identify Happy Path (fastest case) ---
        happy_path_duration = df_cycle["Cycle_Hours"].min()
        happy_path_threshold = happy_path_duration * 1.10  # +10% variance

        # --- Categorize cases ---
        within_variance = df_cycle[df_cycle["Cycle_Hours"] <= happy_path_threshold]
        outside_variance = df_cycle[df_cycle["Cycle_Hours"] > happy_path_threshold]

        num_within = len(within_variance)
        num_outside = len(outside_variance)
        total_cases = len(df_cycle)

        # --- Time saved potential ---
        if num_outside > 0:
            outside_variance["Time_Saved_Potential_Hours"] = (
                outside_variance["Cycle_Hours"] - happy_path_threshold
            )
            total_time_saved = outside_variance["Time_Saved_Potential_Hours"].sum()
            avg_time_saved_per_case = total_time_saved / num_outside
        else:
            total_time_saved = 0
            avg_time_saved_per_case = 0

        # --- Build result ---
        result = {
            "KPI_Name": "Average Time Saved Potential",
            "Happy_Path_Duration_Hours": round(happy_path_duration, 2),
            "Happy_Path_Variance_Threshold_Hours": round(happy_path_threshold, 2),
            "Total_Cases": int(total_cases),
            "Cases_Within_HappyPath_Variance": int(num_within),
            "Cases_Outside_HappyPath_Variance": int(num_outside),
            "Total_Time_Saved_Potential_Hours": round(total_time_saved, 2),
            "Average_Time_Saved_Potential_Per_Case_Hours": round(avg_time_saved_per_case, 2)
        }

        return json.dumps(result, indent=4)
    
    except Exception as e:
        return json.dumps({
            "Error": f"An error occurred during Time Saved Potential calculation: {e}"
        }, indent=4)


def calculate_time_saved_potential(
    event_log_data, 
    case_id_col, 
    start_time_col, 
    complete_time_col
):
    
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, start_time_col, complete_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()

        df_cycle_times['Cycle_Time_Seconds'] = (
            df_cycle_times['Case_End'] - df_cycle_times['Case_Start']
        ).dt.total_seconds()
        
        if df_cycle_times.empty:
            return json.dumps({"Error": "No valid cases found for cycle time calculation."}, indent=4)

        mean_cycle_time_seconds = df_cycle_times['Cycle_Time_Seconds'].mean()
        min_cycle_time_seconds = df_cycle_times['Cycle_Time_Seconds'].min()
        total_cases = len(df_cycle_times)

        avg_time_saved_potential_seconds = max(0, mean_cycle_time_seconds - min_cycle_time_seconds)

        total_time_saved_potential_seconds = avg_time_saved_potential_seconds * total_cases

   
        
        result = {
            "Total_Cases_Analyzed": int(total_cases),
            
            "Mean_Cycle_Time_Seconds": round(mean_cycle_time_seconds, 2),
            "Mean_Cycle_Time_Formatted": seconds_to_dhms(mean_cycle_time_seconds),
            
            "Minimum_Cycle_Time_Seconds": round(min_cycle_time_seconds, 2),
            "Minimum_Cycle_Time_Formatted": seconds_to_dhms(min_cycle_time_seconds),

            "Average_Time_Saved_Potential_Seconds": round(avg_time_saved_potential_seconds, 2),
            "Average_Time_Saved_Potential_Formatted": seconds_to_dhms(avg_time_saved_potential_seconds),
            
            "Total_Time_Saved_Potential_Hours": round(total_time_saved_potential_seconds / 3600, 2),
            "Total_Time_Saved_Potential_Formatted": seconds_to_dhms(total_time_saved_potential_seconds),
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during time saved potential calculation: {e}"}, indent=4)




def calculate_activity_frequency_distribution(event_log_data, activity_col):
    
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        if activity_col not in df.columns:
             return json.dumps({"Error": f"Missing required column in data: {activity_col}"}, indent=4)

        activity_counts = df[activity_col].value_counts()
        total_events = activity_counts.sum()

        if total_events == 0:
            return json.dumps({"Distribution": []}, indent=4)

        distribution = []
        for activity, count in activity_counts.items():
            percentage = (count / total_events) * 100
            distribution.append({
                "activity": activity,
                "count": int(count),
                "percentage": round(percentage, 2)
            })

        result = {
            "Total_Events_Analyzed": int(total_events),
            "Distribution": distribution
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during activity frequency calculation: {e}"}, indent=4)
    




def calculate_happy_path_compliance(
    event_log_data, 
    case_id_col, 
    activity_col, 
    start_time_col, 
    happy_path_data
):
   
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    happy_path_list = None
    
    if isinstance(happy_path_data, dict) and 'happy_paths' in happy_path_data:
        happy_path_list = happy_path_data['happy_paths']

    elif hasattr(happy_path_data, '__iter__') and not isinstance(happy_path_data, str):
        happy_path_list = list(happy_path_data)
    
    if not happy_path_list:
        return json.dumps({"Error": "Happy path definition is missing or empty."}, indent=4)

    try:
        happy_path_list.sort(key=lambda item: item.get('serial_number', -1))
        
        target_path = []
        for item in happy_path_list:
            activity = item.get('activity_name')
            if activity is None:
                return json.dumps({"Error": "Happy path step is missing the 'activity_name' field."}, indent=4)
            target_path.append(activity)

        target_path_tuple = tuple(target_path)
        
    except Exception as e:
        return json.dumps({"Error": f"Failed to sort and extract happy path steps. Check data format: {e}"}, indent=4)

    if not target_path_tuple:
        return json.dumps({"Error": "Target happy path is empty after extraction."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, start_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
      
        df_sorted = df.sort_values(by=[case_id_col, start_time_col])

        def get_case_sequence(group):
            return tuple(group[activity_col].tolist())

        case_sequences = df_sorted.groupby(case_id_col).apply(get_case_sequence, include_groups=False)
        
        total_cases = len(case_sequences)
        if total_cases == 0:
             return json.dumps({"Total_Cases_Analyzed": 0, "Compliance_Rate_Percentage": 0.0}, indent=4)

        compliant_cases_count = 0
        for sequence in case_sequences:
            if sequence == target_path_tuple:
                compliant_cases_count += 1

        non_compliant_cases_count = total_cases - compliant_cases_count
        compliance_rate = (compliant_cases_count / total_cases) * 100
        non_compliance_rate = 100.0 - compliance_rate

        result = {
            "Total_Cases_Analyzed": int(total_cases),
            "Happy_Path_Definition": target_path,
            
            "Compliant_Cases_Count": int(compliant_cases_count),
            "Compliance_Rate_Percentage": round(compliance_rate, 2),
            
            "Non_Compliant_Cases_Count": int(non_compliant_cases_count),
            "Non_Compliance_Rate_Percentage": round(non_compliance_rate, 2),
         
            "Pie_Chart_Data": [
                {"label": "Compliant", "value": round(compliance_rate, 2), "count": int(compliant_cases_count)},
                {"label": "Non-Compliant", "value": round(non_compliance_rate, 2), "count": int(non_compliant_cases_count)}
            ]
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during happy path compliance calculation: {e}"}, indent=4)




def calculate_total_completed_cases(
    event_log_data,
    case_id_col,
    activity_col,
    complete_time_col
):   
    """
    Calculate total completed cases — excluding dropouts.
    A completed case is one whose last activity matches the most frequent final activity.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)

        required_cols = [case_id_col, activity_col, complete_time_col]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        # --- Ensure timestamps are parsed ---
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True, errors="coerce")
        df = df.dropna(subset=[case_id_col, activity_col, complete_time_col])

        # --- Find last event per case ---
        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])
        last_events = df_sorted.groupby(case_id_col).last().reset_index()

        # --- Determine expected final activity (most frequent one) ---
        activity_counts = last_events[activity_col].value_counts()
        if activity_counts.empty:
            return json.dumps({
                "KPI_Name": "Total Completed Cases",
                "Value": 0,
                "Expected_Final_Activity": "N/A",
                "Note": "No activities found in data."
            }, indent=4)
        
        expected_final_activity = activity_counts.index[0]

        # --- Filter completed cases (those that reached expected final activity) ---
        completed_cases = last_events[
            last_events[activity_col] == expected_final_activity
        ]
        num_completed = len(completed_cases)

        result = {
            "KPI_Name": "Total Completed Cases",
            "Value": int(num_completed),
            "Expected_Final_Activity": expected_final_activity
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({
            "Error": f"An error occurred during completed case calculation: {e}"
        }, indent=4)
    


def calculate_happy_path_deviation(
    event_log_data, 
    case_id_col, 
    activity_col, 
    start_time_col,
    complete_time_col, 
    happy_path_data
):
   
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    happy_path_list = None
    if isinstance(happy_path_data, dict) and 'happy_paths' in happy_path_data:
        happy_path_list = happy_path_data['happy_paths']
    elif hasattr(happy_path_data, '__iter__') and not isinstance(happy_path_data, str):
        happy_path_list = list(happy_path_data)
    
    if not happy_path_list:
        return json.dumps({"Error": "Happy path definition is missing or empty."}, indent=4)

    try:
        happy_path_list.sort(key=lambda item: item.get('serial_number', -1))
        target_path = [item.get('activity_name') for item in happy_path_list if item.get('activity_name')]
        target_path_tuple = tuple(target_path)
        happy_path_length = len(target_path_tuple)
        
    except Exception as e:
        return json.dumps({"Error": f"Failed to extract happy path steps: {e}"}, indent=4)

    if happy_path_length == 0:
        return json.dumps({"Error": "Target happy path is empty after extraction."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        required_cols = [case_id_col, activity_col, start_time_col, complete_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
        df_sorted = df.sort_values(by=[case_id_col, start_time_col])

        case_start = df_sorted.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df_sorted.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()
        df_cycle_times['Cycle_Time_Seconds'] = (
            df_cycle_times['Case_End'] - df_cycle_times['Case_Start']
        ).dt.total_seconds()

        case_metrics = df_sorted.groupby(case_id_col).agg(
            sequence=(activity_col, lambda x: tuple(x.tolist())),
            steps_count=(case_id_col, 'size') # Calculate step count
        ).reset_index()

        df_metrics = pd.merge(case_metrics, df_cycle_times[[case_id_col, 'Cycle_Time_Seconds']], on=case_id_col)

        df_metrics['Is_Compliant'] = df_metrics['sequence'] == target_path_tuple

        compliant_times = df_metrics[df_metrics['Is_Compliant']]['Cycle_Time_Seconds']
        if not compliant_times.empty:
           
            t_min_hp = compliant_times.min() 
        else:
            t_min_hp = df_metrics['Cycle_Time_Seconds'].min() if not df_metrics.empty else 0

        df_non_compliant = df_metrics[~df_metrics['Is_Compliant']].copy()
        
        total_non_compliant_cases = len(df_non_compliant)

        if total_non_compliant_cases == 0:
            return json.dumps({
                "Total_Cases_Analyzed": len(df_metrics),
                "Average_Step_Deviation": 0.0,
                "Average_Time_Deviation_Seconds": 0.0,
                "Average_Time_Deviation_Formatted": "0s",
                "Deviation_Activity_Distribution": []
            }, indent=4)

        df_non_compliant['Step_Deviation'] = df_non_compliant['steps_count'] - happy_path_length
  
        df_non_compliant['Time_Deviation_Seconds'] = df_non_compliant['Cycle_Time_Seconds'] - t_min_hp

        avg_step_deviation = df_non_compliant['Step_Deviation'].mean()
        avg_time_deviation_seconds = df_non_compliant['Time_Deviation_Seconds'].mean()

        happy_path_activities = set(target_path_tuple)

        df_non_compliant_events = df[df[case_id_col].isin(df_non_compliant[case_id_col])]

        non_hp_activities = df_non_compliant_events[~df_non_compliant_events[activity_col].isin(happy_path_activities)]        
  
        activity_deviation_counts = non_hp_activities[activity_col].value_counts().nlargest(10)

        activity_deviation_chart = [
            {"activity": act, "deviation_count": int(count)}
            for act, count in activity_deviation_counts.items()
        ]

        result = {
            "Total_Cases_Analyzed": len(df_metrics),
            "Non_Compliant_Cases_Count": total_non_compliant_cases,
            "Happy_Path_Length": happy_path_length,
            
            "Average_Step_Deviation": round(avg_step_deviation, 2),
            "Benchmark_Cycle_Time_Seconds": round(t_min_hp, 2),
            
            "Average_Time_Deviation_Seconds": round(avg_time_deviation_seconds, 2),
            "Average_Time_Deviation_Formatted": seconds_to_dhms(avg_time_deviation_seconds),

            "Deviation_Activity_Distribution": activity_deviation_chart
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during happy path deviation calculation: {e}"}, indent=4)
    




def calculate_skipped_steps_rate(
    event_log_data, 
    case_id_col, 
    activity_col, 
    happy_path_data
):
    """
    Calculates the percentage of cases that skipped at least one required activity
    defined in the Happy Path.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    happy_path_list = None
    if isinstance(happy_path_data, dict) and 'happy_paths' in happy_path_data:
        happy_path_list = happy_path_data['happy_paths']
    elif hasattr(happy_path_data, '__iter__') and not isinstance(happy_path_data, str):
        happy_path_list = list(happy_path_data)
    
    if not happy_path_list:
        return json.dumps({"Error": "Happy path definition is missing or empty."}, indent=4)

    try:
        mandatory_activities = {
            item.get('activity_name') 
            for item in happy_path_list 
            if item.get('activity_name')
        }
        
    except Exception as e:
        return json.dumps({"Error": f"Failed to extract mandatory activities: {e}"}, indent=4)

    if not mandatory_activities:
        return json.dumps({"Error": "Mandatory Happy Path activities set is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        if case_id_col not in df.columns or activity_col not in df.columns:
             missing = [col for col in [case_id_col, activity_col] if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        case_activities = df.groupby(case_id_col)[activity_col].apply(set)
        
        total_cases = len(case_activities)
        if total_cases == 0:
             return json.dumps({"Total_Cases_Analyzed": 0, "Skipped_Steps_Rate_Percentage": 0.0}, indent=4)

        skipped_cases_count = 0
        skipped_activity_counts = {}

        for case_id, actual_activities in case_activities.items():

            missing_activities = mandatory_activities - actual_activities
            
            if missing_activities:
                skipped_cases_count += 1
                for activity in missing_activities:
                    skipped_activity_counts[activity] = skipped_activity_counts.get(activity, 0) + 1

        skipped_steps_rate = (skipped_cases_count / total_cases) * 100

        skipped_activity_chart = sorted(
            [{"activity": act, "skipped_count": count} for act, count in skipped_activity_counts.items()],
            key=lambda x: x['skipped_count'],
            reverse=True
        )[:10]

        # 6. Format Output
        result = {
            "Total_Cases_Analyzed": int(total_cases),
            "Mandatory_Activities_Set": list(mandatory_activities),
            
            "Skipped_Cases_Count": int(skipped_cases_count),
            "Skipped_Steps_Rate_Percentage": round(skipped_steps_rate, 2),

            "Skipped_Activity_Distribution": skipped_activity_chart
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during skipped steps rate calculation: {e}"}, indent=4)




def calculate_case_throughput_and_dropouts(
    event_log_data,
    case_id_col,
    activity_col,
    start_time_col,
    complete_time_col,
    period='M'  # 'D', 'W', 'M'
):
    """
    Calculates completed vs dropout case counts per period based on final activity,
    for bar chart visualization (blue = completed, red = dropouts).
    """
    import pandas as pd, json, math

    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    if period not in ['D', 'W', 'M']:
        return json.dumps({"Error": "Period must be 'D', 'W', or 'M'."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        required_cols = [case_id_col, activity_col, start_time_col, complete_time_col]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return json.dumps({"Error": f"Missing required columns: {missing}"}, indent=4)

        # --- Convert timestamps ---
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True, errors='coerce')
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True, errors='coerce')

        # --- Sort events chronologically ---
        df = df.sort_values(by=[case_id_col, complete_time_col])

        # --- Identify final activity per case ---
        df_last_activities = df.groupby(case_id_col).last().reset_index()
        all_final_activities = df_last_activities[activity_col].value_counts()

        # Most frequent final activity across all cases = "expected final"
        expected_final_activity = all_final_activities.index[0] if not all_final_activities.empty else None

        if expected_final_activity is None:
            return json.dumps({"Error": "Unable to determine final activity."}, indent=4)

        # --- Mark completed/dropout cases ---
        df_last_activities["Is_Completed"] = (
            df_last_activities[activity_col] == expected_final_activity
        )

        # Merge with start times
        case_start = df.groupby(case_id_col)[start_time_col].min().rename("Case_Start")
        df_last_activities = df_last_activities.merge(case_start, on=case_id_col, how="left")

        # --- Assign periods based on case start ---
        if period == 'D':
            df_last_activities["Period"] = df_last_activities["Case_Start"].dt.to_period('D').dt.to_timestamp()
            date_format = "%Y-%m-%d"
            period_label = "day"
        elif period == 'W':
            df_last_activities["Period"] = df_last_activities["Case_Start"].dt.to_period('W').dt.to_timestamp()
            date_format = "%Y-W%W"
            period_label = "week"
        else:
            df_last_activities["Period"] = df_last_activities["Case_Start"].dt.to_period('M').dt.to_timestamp()
            date_format = "%Y-%m"
            period_label = "month"

        # --- Aggregate completed vs dropouts per period ---
        df_summary = (
            df_last_activities.groupby(["Period", "Is_Completed"])[case_id_col]
            .count()
            .unstack(fill_value=0)
            .rename(columns={True: "Completed", False: "Dropouts"})
            .reset_index()
        )

        # --- Format for visualization ---
        bar_chart_data = []
        for _, row in df_summary.iterrows():
            bar_chart_data.append({
                "period": row["Period"].strftime(date_format),
                "completed": int(row.get("Completed", 0)),
                "dropouts": int(row.get("Dropouts", 0))
            })

        total_completed = int(df_last_activities["Is_Completed"].sum())
        total_dropouts = int(len(df_last_activities) - total_completed)

        result = {
            "KPI_Name": "Case Throughput vs Dropouts",
            "Detected_Final_Activity": expected_final_activity,
            "Period_Unit": period_label,
            "Total_Cases": int(len(df_last_activities)),
            "Total_Completed": total_completed,
            "Total_Dropouts": total_dropouts,
            "Throughput_Distribution": bar_chart_data
        }

        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({
            "Error": f"An error occurred during throughput/dropout calculation: {e}"
        }, indent=4)

import math
from datetime import timedelta

def seconds_to_dhms(seconds):
    """Converts a total number of seconds into a days, hours, minutes, seconds string."""
    seconds = abs(seconds)
    days = math.floor(seconds / (3600 * 24))
    seconds %= (3600 * 24)
    hours = math.floor(seconds / 3600)
    seconds %= 3600
    minutes = math.floor(seconds / 60)
    seconds %= 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{round(seconds, 2)}s")

    return " ".join(parts)


def analyze_and_structure_process_datas(
    event_log_data, 
    case_id_col='case_id', 
    activity_col='activity_name', 
    start_time_col='start_time', 
    complete_time_col='complete_time',
    bottleneck_top_n=3,
    project=None
):
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
        df['Event_Duration_Seconds'] = (df[complete_time_col] - df[start_time_col]).dt.total_seconds()
        df['duration'] = df[complete_time_col] - df[start_time_col]
        overall_avg_duration = df['duration'].mean()

        # --- Cycle Times ---
        case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()
        df_cycle_times['Cycle_Time_Seconds'] = (df_cycle_times['Case_End'] - df_cycle_times['Case_Start']).dt.total_seconds()

        total_cases = df_cycle_times[case_id_col].nunique()
        avg_cycle_time_sec = df_cycle_times['Cycle_Time_Seconds'].mean()
        med_cycle_time_sec = df_cycle_times['Cycle_Time_Seconds'].median()
        min_cycle_time_sec = df_cycle_times['Cycle_Time_Seconds'].min()
        max_cycle_time_sec = df_cycle_times['Cycle_Time_Seconds'].max()

        time_span_days = (df[complete_time_col].max() - df[start_time_col].min()).total_seconds() / (3600 * 24)
        throughput_rate = total_cases / time_span_days if time_span_days > 0 else 0
        max_steps_count = df.groupby(case_id_col).size().max()

        df_sequences = df.sort_values(by=[case_id_col, start_time_col]).groupby(case_id_col)[activity_col].apply(lambda x: tuple(x.tolist()))
        variant_counts = df_sequences.value_counts()
        total_variants = len(variant_counts)
        top_5_variants = [
            {"sequence": list(variant), "count": int(count), "percentage": round((count / total_cases) * 100, 2)}
            for variant, count in variant_counts.nlargest(5).items()
        ]

        # --- Standard Path ---
        df_paths = df.groupby(case_id_col)[activity_col].apply(lambda x: ' -> '.join(x)).reset_index(name='Process Path (Variant)')
        df_variants = df_paths['Process Path (Variant)'].value_counts().reset_index()
        most_standard_path_string = df_variants.iloc[0]['Process Path (Variant)']
        standard_activities = [a.strip() for a in most_standard_path_string.split('->')]

        all_activities_df = pd.DataFrame(df[activity_col].unique(), columns=['label'])
        all_activities_df['id'] = (all_activities_df.index + 1).astype(str)
        activity_to_id_map = all_activities_df.set_index('label')['id'].to_dict()

        # --- Directly-Follows Graph ---
        df['Next Activity'] = df.groupby(case_id_col)[activity_col].shift(-1)
        df_transitions = df.dropna(subset=['Next Activity']).copy()
        df_dfg = df_transitions.groupby([activity_col, 'Next Activity']).size().reset_index(name='Frequency')
        df_dfg.columns = ['Source', 'Target', 'Frequency']

        # --- Aggregations ---
        df_avg_time_raw = df.groupby(activity_col).agg(
            avg_duration=('duration', 'mean'),
            total_count=(activity_col, 'size')
        ).reset_index()

        # --- Case Counts ---
        activity_case_counts = df.groupby(activity_col)[case_id_col].nunique().rename('case_count')
        df_avg_time_raw = df_avg_time_raw.merge(activity_case_counts, on=activity_col, how='left')

        df_activity_counts = df.groupby([case_id_col, activity_col]).size().reset_index(name='count')
        df_rework_cases = df_activity_counts[df_activity_counts['count'] > 1]
        rework_case_counts = df_rework_cases.groupby(activity_col)[case_id_col].nunique().rename('rework_case_count').fillna(0).astype(int)
        df_avg_time_raw = df_avg_time_raw.merge(rework_case_counts, on=activity_col, how='left')

        # --- Dropouts ---
        df_last_activities = df.groupby(case_id_col)[activity_col].last()
        expected_end_activity = df_last_activities.mode().iloc[0]
        dropout_counts = df_last_activities[df_last_activities != expected_end_activity].value_counts()
        major_dropout_points = set(dropout_counts.index[:5])
        df_dropout_cases_data = df_last_activities[df_last_activities != expected_end_activity].reset_index(name=activity_col)
        dropout_case_counts = df_dropout_cases_data.groupby(activity_col)[case_id_col].nunique().rename('dropout_case_count').fillna(0).astype(int)
        df_avg_time_raw = df_avg_time_raw.merge(dropout_case_counts, on=activity_col, how='left')

        # --- Bottlenecks ---
        try:
            bottleneck_json = calculate_bottleneck_metrics(
                event_log_data, case_id_col, activity_col, start_time_col, complete_time_col
            )
            bottleneck_data = json.loads(bottleneck_json) if isinstance(bottleneck_json, str) else bottleneck_json
            largest_bottleneck = bottleneck_data.get("Largest_Bottleneck_Metrics", {})
            main_bottleneck_activity = largest_bottleneck.get("Bottleneck_Activity", None)
            bottleneck_occurrence_count = largest_bottleneck.get("Bottleneck_Occurrence_Count", 0)

            df_avg_time_raw["isBottleneck"] = df_avg_time_raw[activity_col] == main_bottleneck_activity
            df_avg_time_raw["bottleneck_occurrence_event_count"] = df_avg_time_raw.apply(
                lambda r: bottleneck_occurrence_count if r["isBottleneck"] else 0, axis=1
            )

        except Exception as e:
            df_avg_time_raw["isBottleneck"] = False
            df_avg_time_raw["bottleneck_occurrence_event_count"] = 0
            print(f"⚠️ Bottleneck analysis failed: {e}")

        # --- Flags ---
        rework_activities = set(rework_case_counts[rework_case_counts > 0].index)
        df_avg_time_raw['hasLoop'] = df_avg_time_raw[activity_col].apply(lambda x: x in rework_activities)
        df_avg_time_raw['isBottleneck'] = df_avg_time_raw['avg_duration'] > overall_avg_duration
        df_avg_time_raw['isDropout'] = df_avg_time_raw[activity_col].apply(lambda x: x in major_dropout_points)

        # --- Merge Master Activities ---
        df_master = pd.DataFrame(standard_activities, columns=['label'])
        df_master = df_master.merge(df_avg_time_raw, left_on='label', right_on=activity_col, how='left')
        df_ids_to_merge = all_activities_df[['label', 'id']].rename(columns={'id': 'activity_id'})
        df_master = df_master.merge(df_ids_to_merge, on='label', how='left')

        # --- Loop Connections ---
        def get_loop_connections(activity_name, has_loop):
            if not has_loop:
                return None
            df_outbound = df_dfg[df_dfg['Source'] == activity_name].sort_values(by='Frequency', ascending=False)
            if df_outbound.empty:
                return None
            loops = []
            current_id = activity_to_id_map.get(activity_name)
            for _, tr in df_outbound.iterrows():
                target = tr['Target']
                if target not in activity_to_id_map:
                    continue
                target_id = activity_to_id_map[target]
                if target == activity_name:
                    loops.append({
                        "from": current_id,
                        "to": target_id,
                        "loop_with": target,
                        "loop_type": "self",
                        "frequency": int(tr['Frequency'])
                    })
                elif int(target_id) < int(current_id):
                    loops.append({
                        "from": current_id,
                        "to": target_id,
                        "loop_with": target,
                        "loop_type": "backward",
                        "frequency": int(tr['Frequency'])
                    })
            return loops if loops else None

        df_master['loopConnections'] = df_master.apply(
            lambda row: get_loop_connections(row['label'], row['hasLoop']),
            axis=1
        )
        df_master['loop_count'] = df_master['loopConnections'].apply(lambda x: len(x) if isinstance(x, list) else 0)

        # --- Cost per Hour (New Section) ---
        from .models import CostPerProcess
        cost_map = {}
        if project:
            cost_map = {
                c.activity_name.lower(): float(c.cost_per_h)
                for c in CostPerProcess.objects.filter(project=project)
            }
        df_master['cost_per_h'] = df_master['label'].apply(lambda x: round(cost_map.get(str(x).lower(), 0.0), 2))

        # --- Duration and Description ---
        if 'avg_duration' in df_master.columns:
            df_master['avg_duration_seconds'] = df_master['avg_duration'].dt.total_seconds().fillna(0)
            df_master.drop(columns=['avg_duration'], inplace=True)

        df_master['id'] = df_master['activity_id']
        df_master['value'] = (df_master['avg_duration_seconds'] / 60).round(2).astype(str)
        df_master['status'] = np.where(df_master['label'] == expected_end_activity, 'final', 'in-progress')
        df_master['owner'] = "N/A"

        def loop_summary_text(row):
            if isinstance(row['loopConnections'], list) and len(row['loopConnections']) > 0:
                conns = [f"from {lc['from']} to {lc['to']} ({lc['loop_type']})" for lc in row['loopConnections']]
                return f"Loop connections: {', '.join(conns)}"
            return "No loops detected."

        df_master['descriptions'] = df_master.apply(
            lambda row: [
                f"Activity executed in {int(row['case_count'])} unique cases." if pd.notna(row['case_count']) else "Case count: 0.",
                f"Total events executed: {int(row['total_count'])} times." if pd.notna(row['total_count']) else "Total events: 0.",
                f"Average processing time: {seconds_to_dhms(row['avg_duration_seconds'])}",
                f"{loop_summary_text(row)}"
            ],
            axis=1
        )

        # --- Final Output ---
        total_process_cost = round(df_master['avg_duration_seconds'].sum(), 2)
        process_flow_nodes = df_master.replace({np.nan: None}).to_dict('records')

        final_output = {
            "global_metrics": {
                "Total_Completed_Cases": int(total_cases),
                "Case_Throughput_Rate_Per_Day": round(throughput_rate, 2),
                "Max_Steps_in_a_Case": int(max_steps_count),
                "Most_Frequent_Path": most_standard_path_string,
                "Cycle_Time": {
                    "Average": seconds_to_dhms(avg_cycle_time_sec),
                    "Median": seconds_to_dhms(med_cycle_time_sec),
                    "Min": seconds_to_dhms(min_cycle_time_sec),
                    "Max": seconds_to_dhms(max_cycle_time_sec),
                },
                "Variant_Analysis": {
                    "Total_Number_of_Process_Variants": int(total_variants),
                    "Top_5_Process_Variants": top_5_variants
                },
                "Rework_Analysis_Simplified": {
                    "Activities_In_Loops_Count": int(df_master['loop_count'].gt(0).sum()),
                    "Time_Lost_Simplified_Basis": "Loop details embedded in 'loopConnections'."
                },
                "Bottleneck_Analysis_Simplified": {
                    "Bottlenecks_Based_on_Avg_Duration_Count": int(df_master['isBottleneck'].sum()),
                    "Time_Lost_Simplified_Basis": "Bottlenecks flagged if avg duration > overall log avg duration."
                },
                "Cost_Analysis": {
                    "Total_Process_Cost": total_process_cost,
                    "Currency": "USD"
                }
            },
            "process_flow_nodes": process_flow_nodes
        }

        return json.dumps(final_output, indent=4)

    except Exception as e:
        return json.dumps({
            "Error": f"An error occurred during process analysis: {e}",
            "global_metrics": {"happy_path": True}
        }, indent=4)


# def analyze_and_structure_process_datas(
#     event_log_data, 
#     case_id_col='case_id', 
#     activity_col='activity_name', 
#     start_time_col='start_time', 
#     complete_time_col='complete_time',
#     bottleneck_top_n=3,
#     project=None
# ):
#     """
#     Calculates key process mining metrics and structures the output into a global
#     metrics summary and an annotated process flow node list.
#     Metrics for bottleneck, loop, and dropout counts are now based on affected 
#     'case counts' rather than total 'event counts'.
    
#     The bottleneck count now specifically calculates the number of events where 
#     the duration exceeded the activity's average duration, providing a more 
#     accurate measure of 'bottleneck occurrences'.
#     """
#     if not event_log_data:
#         return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
#     try:
#         df = pd.DataFrame(event_log_data)

#         # --- 1. Prepare Data and Calculate Durations ---
#         df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
#         df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
#         df['Event_Duration_Seconds'] = (df[complete_time_col] - df[start_time_col]).dt.total_seconds()
#         df['duration'] = df[complete_time_col] - df[start_time_col]
#         overall_avg_duration = df['duration'].mean()

#         # --- Case cycle times (omitted for brevity) ---
#         case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
#         case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
#         df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()
#         df_cycle_times['Cycle_Time_Seconds'] = (df_cycle_times['Case_End'] - df_cycle_times['Case_Start']).dt.total_seconds()

#         # --- 2. Global Metrics (omitted for brevity) ---
#         total_cases = df_cycle_times[case_id_col].nunique()
#         avg_cycle_time_sec = df_cycle_times['Cycle_Time_Seconds'].mean()
#         med_cycle_time_sec = df_cycle_times['Cycle_Time_Seconds'].median()
#         min_cycle_time_sec = df_cycle_times['Cycle_Time_Seconds'].min()
#         max_cycle_time_sec = df_cycle_times['Cycle_Time_Seconds'].max()

#         time_span_days = (df[complete_time_col].max() - df[start_time_col].min()).total_seconds() / (3600 * 24)
#         throughput_rate = total_cases / time_span_days if time_span_days > 0 else 0
#         max_steps_count = df.groupby(case_id_col).size().max()

#         df_sequences = df.sort_values(by=[case_id_col, start_time_col]).groupby(case_id_col)[activity_col].apply(lambda x: tuple(x.tolist()))
#         variant_counts = df_sequences.value_counts()
#         total_variants = len(variant_counts)
#         top_5_variants = [
#             {"sequence": list(variant), "count": int(count), "percentage": round((count / total_cases) * 100, 2)}
#             for variant, count in variant_counts.nlargest(5).items()
#         ]

#         # --- 3. Activity-Level Metrics ---
#         # Standard path logic (omitted for brevity)
#         df_paths = df.groupby(case_id_col)[activity_col].apply(lambda x: ' -> '.join(x)).reset_index(name='Process Path (Variant)')
#         df_variants = df_paths['Process Path (Variant)'].value_counts().reset_index()
#         most_standard_path_string = df_variants.iloc[0]['Process Path (Variant)']
#         standard_activities = [a.strip() for a in most_standard_path_string.split('->')]

#         all_activities_df = pd.DataFrame(df[activity_col].unique(), columns=['label'])
#         all_activities_df['id'] = (all_activities_df.index + 1).astype(str)
#         activity_to_id_map = all_activities_df.set_index('label')['id'].to_dict()

#         df['Next Activity'] = df.groupby(case_id_col)[activity_col].shift(-1)
#         df_transitions = df.dropna(subset=['Next Activity']).copy()
#         df_dfg = df_transitions.groupby([activity_col, 'Next Activity']).size().reset_index(name='count')
#         df_dfg.columns = ['Source', 'Target', 'Frequency']

#         # --- Base Metrics Calculation ---
#         df_avg_time_raw = df.groupby(activity_col).agg(
#             avg_duration=('duration', 'mean'),
#             total_count=(activity_col, 'size') # Total Event Count
#         ).reset_index()

#         # --- NEW: Case-based Counts ---
#         df_activity_counts = df.groupby([case_id_col, activity_col]).size().reset_index(name='count')
        
#         # 1. Activity Case Count (How many unique cases used this activity?)
#         activity_case_counts = df.groupby(activity_col)[case_id_col].nunique().rename('case_count')
#         df_avg_time_raw = df_avg_time_raw.merge(activity_case_counts, on=activity_col, how='left')
        
#         # 2. Rework Case Count (How many unique cases looped at this activity?)
#         df_rework_cases = df_activity_counts[df_activity_counts['count'] > 1]
#         rework_case_counts = df_rework_cases.groupby(activity_col)[case_id_col].nunique().rename('rework_case_count').fillna(0).astype(int)
#         df_avg_time_raw = df_avg_time_raw.merge(rework_case_counts, on=activity_col, how='left')

#         # 3. Dropout Case Count (How many unique cases ended prematurely at this activity?)
#         df_last_activities = df.groupby(case_id_col)[activity_col].last()
#         expected_end_activity = df_last_activities.mode().iloc[0]
#         dropout_counts = df_last_activities[df_last_activities != expected_end_activity].value_counts()
#         major_dropout_points = set(dropout_counts.index[:5]) # Flag for top 5 dropout points
        
#         df_dropout_cases_data = df_last_activities[df_last_activities != expected_end_activity].reset_index(name=activity_col)
#         dropout_case_counts = df_dropout_cases_data.groupby(activity_col)[case_id_col].nunique().rename('dropout_case_count').fillna(0).astype(int)
#         df_avg_time_raw = df_avg_time_raw.merge(dropout_case_counts, on=activity_col, how='left')


#         # 4. Bottleneck Occurrence Event Count (Count of events where duration > activity's average)
#         avg_event_time_seconds = df.groupby(activity_col)['Event_Duration_Seconds'].mean().rename('Average_Time_Seconds')
#         df_bottleneck_check = df.merge(avg_event_time_seconds, on=activity_col, how='left')
#         df_bottleneck_check['is_bottleneck_event'] = df_bottleneck_check['Event_Duration_Seconds'] > df_bottleneck_check['Average_Time_Seconds']

#         bottleneck_event_counts = df_bottleneck_check[df_bottleneck_check['is_bottleneck_event']].groupby(activity_col).size().rename('bottleneck_occurrence_event_count')
#         df_avg_time_raw = df_avg_time_raw.merge(bottleneck_event_counts, on=activity_col, how='left')
#         df_avg_time_raw['bottleneck_occurrence_event_count'] = df_avg_time_raw['bottleneck_occurrence_event_count'].fillna(0).astype(int)


#         # --- Flagging (Using sets derived from case counts) ---
#         rework_activities = set(rework_case_counts[rework_case_counts > 0].index)
#         df_avg_time_raw['hasLoop'] = df_avg_time_raw[activity_col].apply(lambda x: x in rework_activities)
#         df_avg_time_raw['isBottleneck'] = df_avg_time_raw['avg_duration'] > overall_avg_duration
#         df_avg_time_raw['isDropout'] = df_avg_time_raw[activity_col].apply(lambda x: x in major_dropout_points)


#         # --- 4. Cost Integration (omitted for brevity) ---
#         cost_map = {}
#         if project:
#             try:
#                 cost_map = {c.activity_name: float(c.cost_per_h) for c in CostPerProcess.objects.filter(project=project)}
#             except Exception as e:
#                 print(f"⚠️ Cost mapping failed: {e}") 

#         df_avg_time_raw['cost_per_h'] = df_avg_time_raw[activity_col].map(cost_map).fillna(0.0)
#         df_avg_time_raw['avg_duration_h'] = df_avg_time_raw['avg_duration'].dt.total_seconds() / 3600.0
#         df_avg_time_raw['estimated_cost'] = df_avg_time_raw['avg_duration_h'] * df_avg_time_raw['cost_per_h']

#         # --- 5. Loop Connection Logic (omitted for brevity) ---
#         def get_loop_connections(row):
#             activity = row['label']
#             if not row['hasLoop']: 
#                 return None
#             # ... (rest of loop logic remains unchanged)
#             current_id = activity_to_id_map.get(activity)
#             if current_id is None:
#                 return None

#             df_outbound = df_dfg[df_dfg['Source'] == activity].sort_values(by='Frequency', ascending=False)
#             valid_backward_targets = {}

#             for _, transition in df_outbound.iterrows():
#                 target = transition['Target']
#                 target_id = activity_to_id_map.get(target)
#                 if target_id is None:
#                     continue
#                 if target == activity:
#                     return {"from": current_id, "to": target_id}
#                 if int(target_id) < int(current_id):
#                     valid_backward_targets[target_id] = transition['Frequency']

#             if valid_backward_targets:
#                 best_target_id = max(valid_backward_targets.keys(), key=int)
#                 return {"from": current_id, "to": best_target_id}

#             if not df_outbound.empty:
#                 most_frequent_transition = df_outbound.iloc[0]
#                 target = most_frequent_transition['Target']
#                 target_id = activity_to_id_map.get(target)
#                 if target_id and target_id != current_id:
#                     return {"from": current_id, "to": target_id}
#             return None

#         # --- 6. Process Flow Nodes ---
#         df_master = pd.DataFrame(standard_activities, columns=['label'])
#         df_master = df_master.merge(df_avg_time_raw, left_on='label', right_on=activity_col, how='left')
#         df_ids_to_merge = all_activities_df[['label', 'id']].rename(columns={'id': 'activity_id'})
#         df_master = df_master.merge(df_ids_to_merge, on='label', how='left')
        
#         # 🟢 FIX & ENHANCEMENT: Use conditional Occurrence Counts for Bottleneck
#         # Bottleneck: How many times did this activity exceed its OWN average processing time? 
#         df_master['bottleneck_count'] = df_master['bottleneck_occurrence_event_count'].where(df_master['isBottleneck'], 0).fillna(0).astype(int)
        
#         # Loop: How many cases had rework/loops at this activity? (if it has loops)
#         df_master['loop_count'] = df_master['rework_case_count'].where(df_master['hasLoop'], 0).fillna(0).astype(int)
        
#         # Dropout: How many cases dropped out at this activity? (if it's a major dropout point)
#         df_master['dropout_count'] = df_master['dropout_case_count'].where(df_master['isDropout'], 0).fillna(0).astype(int)
#         # 🟢 END FIX & ENHANCEMENT

#         df_master['id'] = df_master['activity_id']
#         df_master['value'] = df_master['avg_duration'].dt.total_seconds().fillna(0) / 60
#         df_master['value'] = df_master['value'].round(2).astype(str)
#         df_master['loopConnections'] = df_master.apply(lambda row: get_loop_connections({'label': row['label'], 'hasLoop': row['hasLoop']}), axis=1)
#         df_master['status'] = np.where(df_master['label'] == expected_end_activity, 'final', 'in-progress')
#         df_master['owner'] = "N/A"

#         # Update descriptions to use the new, more sensible case counts for context
#         df_master['descriptions'] = df_master.apply(
#             lambda row: [
#                 f"Activity was executed in {int(row['case_count'])} unique cases." if pd.notna(row['case_count']) else "Case count: 0.",
#                 f"Total events executed: {int(row['total_count'])} times." if pd.notna(row['total_count']) else "Total events: 0.",
#                 f"Average processing time: {seconds_to_dhms(row['avg_duration'].total_seconds() if pd.notna(row['avg_duration']) else 0)}",
#                 f"Cost per hour: {row['cost_per_h']}",
#                 f"Estimated cost per case: {round(row['estimated_cost'], 2)}"
#             ],
#             axis=1
#         )

#         cols_to_drop = [activity_col, 'avg_duration', 'total_count', 'activity_id', 'case_count', 'rework_case_count', 'dropout_case_count', 'bottleneck_occurrence_event_count']
#         df_master.drop(columns=cols_to_drop, inplace=True, errors='ignore')

#         process_flow_nodes = df_master.rename(columns={'label': 'label'}).replace({np.nan: None, None: None}).to_dict('records')
#         for node in process_flow_nodes:
#             node['owner'] = node.get('owner', 'N/A')
#             node['extras'] = node.get('extras', [])
        
#         # --- 7. Final Output (omitted for brevity) ---
#         total_process_cost = round(df_avg_time_raw['estimated_cost'].sum(), 2)
#         final_output = {
#             "global_metrics": {
#                 "Total_Completed_Cases": int(total_cases),
#                 "Case_Throughput_Rate_Per_Day": round(throughput_rate, 2),
#                 "Max_Steps_in_a_Case": int(max_steps_count),
#                 "Most_Frequent_Path": most_standard_path_string,
#                 "Cycle_Time": {
#                     "Average": seconds_to_dhms(avg_cycle_time_sec),
#                     "Median": seconds_to_dhms(med_cycle_time_sec),
#                     "Min": seconds_to_dhms(min_cycle_time_sec),
#                     "Max": seconds_to_dhms(max_cycle_time_sec),
#                 },
#                 "Variant_Analysis": {
#                     "Total_Number_of_Process_Variants": int(total_variants),
#                     "Top_5_Process_Variants": top_5_variants
#                 },
#                 "Rework_Analysis_Simplified": {
#                     # This now counts the number of activities that had ANY rework cases
#                     "Activities_In_Loops_Count": len(rework_activities), 
#                     "Time_Lost_Simplified_Basis": "Loop/Rework analysis is now embedded in 'process_flow_nodes' loop_count (cases affected).",
#                 },
#                 "Bottleneck_Analysis_Simplified": {
#                     "Bottlenecks_Based_on_Avg_Duration_Count": len(df_master[df_master['isBottleneck']]),
#                     "Time_Lost_Simplified_Basis": "Bottlenecks flagged if avg duration > overall log avg duration.",
#                 },
#                 "Cost_Analysis": { 
#                     "Total_Process_Cost": total_process_cost,
#                     "Currency": "USD"
#                 }
#             },
#             "process_flow_nodes": process_flow_nodes
#         }

#         return json.dumps(final_output, indent=4)

#     except Exception as e:
#         return json.dumps({"Error": f"An error occurred during process analysis: {e}"}, indent=4)



import pandas as pd
import json
import math
import numpy as np
from datetime import timedelta

# --- Helper Function for Formatting Time ---
def seconds_to_dhms(seconds):
    """Converts a total number of seconds into a days, hours, minutes, seconds string."""
    seconds = abs(seconds)
    days = math.floor(seconds / (3600 * 24))
    seconds %= (3600 * 24)
    hours = math.floor(seconds / 3600)
    seconds %= 3600
    minutes = math.floor(seconds / 60)
    seconds %= 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{round(seconds, 2)}s")

    return " ".join(parts)



from collections import defaultdict, Counter


def infer_step_index(df, case_id_col, start_time_col):
    df = df.sort_values([case_id_col, start_time_col]).copy()
    df["step_index"] = df.groupby(case_id_col).cumcount() + 1
    return df


def infer_ideal_positions(df, case_id_col, activity_col):
    pos_counts = defaultdict(Counter)
    for _, row in df[[activity_col, "step_index"]].iterrows():
        pos_counts[row[activity_col]][int(row["step_index"])] += 1

    ideal_positions = {}
    for act, counter in pos_counts.items():
        most_common = counter.most_common()
        if not most_common:
            continue
        top_freq = most_common[0][1]
        candidates = [pos for pos, freq in most_common if freq == top_freq]
        ideal_positions[act] = min(candidates)
    return ideal_positions


def compute_ideal_times(df, activity_col, ideal_positions):
    ideal_times = {}
    for act, pos in ideal_positions.items():
        mask = (df[activity_col] == act) & (df["step_index"] == pos)
        ideal_times[act] = float(df.loc[mask, "Event_Duration_Seconds"].median()) if mask.any() else None
    return ideal_times


def detect_loops(df, case_id_col, activity_col):
    loop_records = []
    loop_activities = set()
    for case_id, group in df.groupby(case_id_col):
        last_seen = {}
        for _, row in group.iterrows():
            act = row[activity_col]
            idx = int(row["step_index"])
            if act in last_seen:
                loop_records.append({"case_id": case_id, "activity": act, "from": last_seen[act], "to": idx})
                loop_activities.add(act)
            last_seen[act] = idx
    return loop_records, loop_activities


def detect_dropouts(df, activity_col, case_id_col, ideal_positions):
    activities = df[activity_col].unique().tolist()
    dropout_cases_by_activity = {a: set() for a in activities}

    ideal_sequence = sorted(ideal_positions.items(), key=lambda x: x[1])
    ideal_steps = [a for a, _ in ideal_sequence]

    for case_id, group in df.groupby(case_id_col):
        performed_steps = set(group[activity_col].tolist())
        missing = [s for s in ideal_steps if s not in performed_steps]
        for m in missing:
            dropout_cases_by_activity[m].add(case_id)

    is_dropout_map = {a: len(cases) > 0 for a, cases in dropout_cases_by_activity.items()}
    return is_dropout_map, dropout_cases_by_activity


def detect_bottlenecks(activity_metrics, ideal_times, activity_col, threshold_sec: int = 3600):
    """
    Detect activities that take significantly longer than their ideal duration.
    A bottleneck is flagged only if the delay (actual - ideal) > threshold_sec.
    Default threshold: 3600 seconds (1 hour).
    """
    is_bottleneck_map = {}
    bottleneck_delta_map = {}

    for _, r in activity_metrics.iterrows():
        act = r[activity_col]
        actual_time = float(r["avg_duration"]) if pd.notnull(r["avg_duration"]) else 0.0
        ideal_time_sec = ideal_times.get(act)

        if ideal_time_sec is None or ideal_time_sec == 0:
            is_bottleneck_map[act] = False
            bottleneck_delta_map[act] = 0.0
            continue

        delay = actual_time - ideal_time_sec

        if delay > threshold_sec:
            is_bottleneck_map[act] = True
            bottleneck_delta_map[act] = round(delay, 2)
        else:
            is_bottleneck_map[act] = False
            bottleneck_delta_map[act] = 0.0

    return is_bottleneck_map, bottleneck_delta_map


# ---------------------------- MAIN FUNCTION ----------------------------

def analyze_and_structure_process_data(
    event_log_data,
    case_id_col='case_id',
    activity_col='activity_name',
    start_time_col='start_time',
    complete_time_col='complete_time',
    owner_map=None,
    description_map=None,
    extras_map=None,
):
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
        df["Event_Duration_Seconds"] = (df[complete_time_col] - df[start_time_col]).dt.total_seconds()

        df = infer_step_index(df, case_id_col, start_time_col)
        ideal_positions = infer_ideal_positions(df, case_id_col, activity_col)
        ideal_times = compute_ideal_times(df, activity_col, ideal_positions)

        activity_metrics = (
            df.groupby(activity_col)
            .agg(
                avg_duration=("Event_Duration_Seconds", "mean"),
                total_count=(activity_col, "size"),
            )
            .reset_index()
        )

        loop_records, loop_activities = detect_loops(df, case_id_col, activity_col)
        is_dropout_map, dropout_cases_by_activity = detect_dropouts(df, activity_col, case_id_col, ideal_positions)
        is_bottleneck_map, bottleneck_delta_map = detect_bottlenecks(activity_metrics, ideal_times, activity_col)

        def sort_key(act_name):
            return (ideal_positions.get(act_name, 999999), act_name.lower())

        ordered_activities = sorted(activity_metrics[activity_col].tolist(), key=sort_key)
        loop_by_activity = defaultdict(list)
        for rec in loop_records:
            loop_by_activity[rec["activity"]].append(
                {"case_id": rec["case_id"], "from": rec["from"], "to": rec["to"]}
            )

        process_flow_nodes = []
        for idx, act in enumerate(ordered_activities, start=1):
            metrics = activity_metrics.loc[activity_metrics[activity_col] == act].iloc[0]
            avg_duration = float(metrics["avg_duration"])
            total_count = int(metrics["total_count"])

            descriptions = [f"{act} occurred {total_count} times in the log."]
            if is_bottleneck_map.get(act):
                delay = bottleneck_delta_map.get(act, 0.0)
                descriptions.append(f"There is a bottleneck in this step ({act}) — delay: {delay} sec.")
            if is_dropout_map.get(act):
                ex_cases = sorted(list(dropout_cases_by_activity.get(act, [])))
                if ex_cases:
                    case_list = ", ".join(ex_cases[:5])
                    descriptions.append(f"There is dropout in case(s): {case_list} — \"{act}\" was missed from these processes.")

            node = {
                "id": str(idx),
                "label": act,
                "value": str(round(avg_duration / 60, 2)),
                "status": "in-progress",
                "owner": owner_map.get(act, "Unassigned") if owner_map else "Unassigned",
                "descriptions": descriptions,
                "Is_Bottlenecks": "Yes" if is_bottleneck_map.get(act) else "No",
                "Is_Dropout": "Yes" if is_dropout_map.get(act) else "No",
                "hasLoop": act in loop_activities,
                "extras": extras_map.get(act, []) if extras_map else [],
            }

            if loop_by_activity.get(act):
                node["loopConnections"] = loop_by_activity[act]
            process_flow_nodes.append(node)

        return json.dumps({"process_flow_nodes": process_flow_nodes}, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred: {e}"}, indent=4)




def calculate_kpi_summary(event_log_data, case_id_col, activity_col, timestamp_start, timestamp_end, office_start_hour, office_end_hour):
   
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        df[timestamp_start] = pd.to_datetime(df[timestamp_start], utc=True)
        df[timestamp_end] = pd.to_datetime(df[timestamp_end], utc=True)
        
        df = df.sort_values(by=[case_id_col, timestamp_start]).reset_index(drop=True)

        case_start = df.groupby(case_id_col)[timestamp_start].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[timestamp_end].max().rename('Case_End')
        df_cases = pd.merge(case_start, case_end, on=case_id_col).reset_index()

        total_cases = df_cases[case_id_col].nunique()
        completed_cases = total_cases 

        if total_cases == 0:
            return json.dumps({"Warning": "No cases found in the event log."}, indent=4)

        dropout_rate = 0.0

        
        df_cases['Adjusted_Cycle_Time_Seconds'] = df_cases.apply(
            lambda row: calculate_net_working_time(
                row['Case_Start'], 
                row['Case_End'], 
                office_start_hour, 
                office_end_hour
            ), 
            axis=1
        )

        df_cases['Adjusted_Cycle_Time_Hours'] = df_cases['Adjusted_Cycle_Time_Seconds'] / 3600.0

        median_cycle_time_h = df_cases['Adjusted_Cycle_Time_Hours'].median()
        average_cycle_time_h = df_cases['Adjusted_Cycle_Time_Hours'].mean()
        variance_cycle_time_h2 = df_cases['Adjusted_Cycle_Time_Hours'].var()
        dev_cycle_time_h = df_cases['Adjusted_Cycle_Time_Hours'].std()
        min_cycle_time_h = df_cases['Adjusted_Cycle_Time_Hours'].min()
        max_cycle_time_h = df_cases['Adjusted_Cycle_Time_Hours'].max()

        
        steps_per_case = df.groupby(case_id_col).size()
        median_steps = steps_per_case.median()
        average_steps = steps_per_case.mean()

        looped_cases_df = df.groupby(case_id_col)[activity_col].apply(lambda x: x.duplicated().any())
        total_loops_cases = looped_cases_df.sum()
        
        loops_ratio = (total_loops_cases / total_cases) * 100

        df['Next_Start'] = df.groupby(case_id_col)[timestamp_start].shift(-1)
        df['Idle_Time_Seconds'] = (df['Next_Start'] - df[timestamp_end]).dt.total_seconds()
        

        df_idle = df[df['Idle_Time_Seconds'].notna() & (df['Idle_Time_Seconds'] >= 0)].copy()

        idle_time_by_activity = df_idle.groupby(activity_col)['Idle_Time_Seconds'].mean()
        
        if idle_time_by_activity.empty:
             largest_bottleneck = "N/A"
             bottleneck_severity_min = 0.0
        else:

            idle_time_by_activity_min = idle_time_by_activity / 60.0

            largest_bottleneck = idle_time_by_activity_min.idxmax()
            bottleneck_severity_min = idle_time_by_activity_min.max()

        payment_monitoring_severity = idle_time_by_activity_min.get('Payment Monitoring', 0.0)
        receipt_reconciled_severity = idle_time_by_activity_min.get('Receipt Reconciled', 0.0)


      
        results = {
            "Total_Cases": int(total_cases),
            "Completed_Cases": int(completed_cases),
            "Dropout_Rate_pct": round(dropout_rate, 2),
            "Median_Cycle_Time_h": round(median_cycle_time_h, 2) if not pd.isna(median_cycle_time_h) else 0.0,
            "Average_Cycle_Time_h": round(average_cycle_time_h, 2) if not pd.isna(average_cycle_time_h) else 0.0,
            "Cycle_Time_Variance_h2": round(variance_cycle_time_h2, 2) if not pd.isna(variance_cycle_time_h2) else 0.0,
            "Dev_Cycle_Time_h": round(dev_cycle_time_h, 2) if not pd.isna(dev_cycle_time_h) else 0.0,
            "Min_Cycle_Time_h": round(min_cycle_time_h, 2) if not pd.isna(min_cycle_time_h) else 0.0,
            "Max_Cycle_Time_h": round(max_cycle_time_h, 2) if not pd.isna(max_cycle_time_h) else 0.0,
            "Median_Steps_Case": round(median_steps, 2) if not pd.isna(median_steps) else 0.0,
            "Average_Steps_Case": round(average_steps, 2) if not pd.isna(average_steps) else 0.0,
            "Total_Loops_Cases": int(total_loops_cases),
            "Loops_Ratio_pct": round(loops_ratio, 2),
            
            "Largest_Bottleneck_Activity": largest_bottleneck,
            "Bottleneck_Severity_min": round(bottleneck_severity_min, 2),
            
            "Payment_Monitoring_Severity_min": round(payment_monitoring_severity, 2),
            "Receipt_Reconciled_Severity_min": round(receipt_reconciled_severity, 2),
        }

        return json.dumps(results, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during KPI calculation: {e}"}, indent=4)
    


    
import pandas as pd
from typing import List, Optional

def filter_event_log_pre_kpi(
    df: pd.DataFrame,
    case_id_col: str,
    variant_col: str,
    timestamp_start_col: str,
    timestamp_complete_col: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    selected_variants: Optional[List[str]] = None,
    min_cycle_time: Optional[float] = None,
    max_cycle_time: Optional[float] = None,
    time_unit: str = "hours"
) -> pd.DataFrame:
    
    filtered_df = df.copy()
    try:
        filtered_df[timestamp_start_col] = pd.to_datetime(
            filtered_df[timestamp_start_col], errors='coerce'
        )
       
        filtered_df[timestamp_complete_col] = pd.to_datetime(
            filtered_df[timestamp_complete_col], errors='coerce'
        )
    except KeyError as e:
       
        raise ValueError(f"Missing timestamp column in CSV: {e}")
    except Exception as e:        
        raise ValueError(f"Error converting timestamps to datetime: {e}")

    filtered_df[timestamp_start_col] = pd.to_datetime(filtered_df[timestamp_start_col])

    case_start_times = filtered_df.groupby(case_id_col)[timestamp_start_col].min().reset_index()
    
    if start_date:
        start_dt = pd.to_datetime(start_date)
        valid_cases = case_start_times[case_start_times[timestamp_start_col] >= start_dt][case_id_col]
        filtered_df = filtered_df[filtered_df[case_id_col].isin(valid_cases)]
        
    if end_date:
        end_dt = pd.to_datetime(end_date)
        valid_cases = case_start_times[case_start_times[timestamp_start_col] <= end_dt][case_id_col]

        filtered_df = filtered_df[filtered_df[case_id_col].isin(valid_cases)]

    if selected_variants and len(selected_variants) > 0:
        

        case_activities = filtered_df.groupby(case_id_col)[variant_col].apply(list).reset_index(name='activities')

        case_activities['calculated_variant_path'] = case_activities['activities'].apply(
            lambda x: ' -> '.join(x)
        )

        clean_calculated_paths = case_activities['calculated_variant_path'].str.lower().str.strip()

        clean_selected_variants = [v.lower().strip() for v in selected_variants]

        matching_indices = clean_calculated_paths.isin(clean_selected_variants)
      
        matching_case_ids = case_activities[matching_indices][case_id_col].unique()

        filtered_df = filtered_df[filtered_df[case_id_col].isin(matching_case_ids)]

    if min_cycle_time is not None or max_cycle_time is not None:
        
        if filtered_df.empty:
             return filtered_df

        case_times = filtered_df.groupby(case_id_col).agg(
            case_start=(timestamp_start_col, 'min'),
            case_end=(timestamp_complete_col, 'max')
        ).reset_index()
        

        case_times['case_start'] = pd.to_datetime(case_times['case_start'])
        case_times['case_end'] = pd.to_datetime(case_times['case_end'])

        case_times['cycle_time_delta'] = case_times['case_end'] - case_times['case_start']

        unit_factor = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
        divisor = unit_factor.get(time_unit.lower(), 3600)
        
        case_times['cycle_time_unit'] = case_times['cycle_time_delta'].dt.total_seconds() / divisor
        
        valid_cycle_time_cases = case_times.copy()
        
        if min_cycle_time is not None:
            valid_cycle_time_cases = valid_cycle_time_cases[
                valid_cycle_time_cases['cycle_time_unit'] >= min_cycle_time
            ]
            
        if max_cycle_time is not None:
            valid_cycle_time_cases = valid_cycle_time_cases[
                valid_cycle_time_cases['cycle_time_unit'] <= max_cycle_time
            ]
            
        filtered_df = filtered_df[
            filtered_df[case_id_col].isin(valid_cycle_time_cases[case_id_col])
        ]

    return filtered_df



import pandas as pd
import json
from .models import HappyPath

def calculate_cost_per_process(event_log_data, activity_col, start_time_col, complete_time_col, project):
   
    if not event_log_data:
        return json.dumps({
            "total_cost_all_activities": 0.0,
            "activities_cost_breakdown": [],
            "currency": "USD"
        })

    df = pd.DataFrame(event_log_data)
    df[start_time_col] = pd.to_datetime(df[start_time_col], errors='coerce', utc=True)
    df[complete_time_col] = pd.to_datetime(df[complete_time_col], errors='coerce', utc=True)

    happy_steps = HappyPath.objects.filter(project=project)
    if not happy_steps.exists():
        return json.dumps({
            "total_cost_all_activities": 0.0,
            "activities_cost_breakdown": [],
            "note": "No HappyPath data found for this project.",
            "currency": "USD"
        })

    activity_counts = df[activity_col].value_counts().to_dict()

    cost_summary = []
    total_cost = 0.0

    for step in happy_steps:
        activity = step.activity_name.strip()
        count = activity_counts.get(activity, 0)
        step_cost = float(step.cost or 0.0)
        total_activity_cost = round(count * step_cost, 2)
        total_cost += total_activity_cost

        cost_summary.append({
            "activity_name": activity,
            "occurrences": count,
            "cost_per_occurrence": step_cost,
            "total_activity_cost": total_activity_cost
        })

    result = {
        "total_cost_all_activities": round(total_cost, 2),
        "activities_cost_breakdown": cost_summary,
        "currency": "USD",
        "project_id": project.id,
        "process_name": project.process
    }

    return json.dumps(result, indent=4)



def calculate_average_deviation_from_happy_path(event_log_data, case_id_col, activity_col, start_time_col, complete_time_col, project):
 
    if not event_log_data:
        return json.dumps({
            "avg_step_deviation": 0.0,
            "avg_time_deviation_hours": 0.0,
            "cases_analyzed": 0,
            "note": "No event log data provided."
        })

    df = pd.DataFrame(event_log_data)
    if df.empty or any(c not in df.columns for c in [case_id_col, activity_col, start_time_col, complete_time_col]):
        return json.dumps({
            "avg_step_deviation": 0.0,
            "avg_time_deviation_hours": 0.0,
            "cases_analyzed": 0,
            "note": "Missing required columns in event log."
        })

    happy_steps = HappyPath.objects.filter(project=project).order_by("serial_number")
    happy_activities = [step.activity_name.strip() for step in happy_steps]
    happy_total_minutes = sum(float(step.average_time_minutes) for step in happy_steps)

    if not happy_activities:
        return json.dumps({
            "avg_step_deviation": 0.0,
            "avg_time_deviation_hours": 0.0,
            "cases_analyzed": 0,
            "note": "No Happy Path defined for this project."
        })

    df[start_time_col] = pd.to_datetime(df[start_time_col], errors='coerce', utc=True)
    df[complete_time_col] = pd.to_datetime(df[complete_time_col], errors='coerce', utc=True)

    step_deviations = []
    time_deviations = []

    for case_id, group in df.groupby(case_id_col):
        activities = group[activity_col].dropna().astype(str).str.strip().tolist()

        missing = len([a for a in happy_activities if a not in activities])
        extra = len([a for a in activities if a not in happy_activities])
        step_dev = missing + extra
        step_deviations.append(step_dev)

        case_start = group[start_time_col].min()
        case_end = group[complete_time_col].max()
        case_duration_hours = (case_end - case_start).total_seconds() / 3600 if pd.notna(case_start) and pd.notna(case_end) else 0
        happy_duration_hours = happy_total_minutes / 60
        time_dev = abs(case_duration_hours - happy_duration_hours)
        time_deviations.append(time_dev)

    
    avg_step_dev = round(sum(step_deviations) / len(step_deviations), 2) if step_deviations else 0.0
    avg_time_dev = round(sum(time_deviations) / len(time_deviations), 2) if time_deviations else 0.0

    result = {
        "avg_step_deviation": avg_step_dev,
        "avg_time_deviation_hours": avg_time_dev,
        "cases_analyzed": len(step_deviations),
        "happy_path_steps": happy_activities,
        "happy_path_expected_duration_hours": round(happy_total_minutes / 60, 2)
    }

    return json.dumps(result, indent=4)




def calculate_happy_path_compliance_rate(event_log_data, case_id_col, activity_col, project):
   
    if not event_log_data:
        return json.dumps({
            "happy_path_compliance_rate": 0.0,
            "total_cases": 0,
            "compliant_cases": 0,
            "non_compliant_cases": 0,
            "note": "No event log data."
        })

    df = pd.DataFrame(event_log_data)
    if df.empty or any(c not in df.columns for c in [case_id_col, activity_col]):
        return json.dumps({
            "happy_path_compliance_rate": 0.0,
            "total_cases": 0,
            "compliant_cases": 0,
            "non_compliant_cases": 0,
            "note": "Missing required columns."
        })

    happy_steps = HappyPath.objects.filter(project=project).order_by("serial_number")
    happy_sequence = [step.activity_name.strip() for step in happy_steps]

    if not happy_sequence:
        return json.dumps({
            "happy_path_compliance_rate": 0.0,
            "total_cases": 0,
            "compliant_cases": 0,
            "non_compliant_cases": 0,
            "note": "No Happy Path defined for this project."
        })

    total_cases = 0
    compliant_cases = 0

    for case_id, group in df.groupby(case_id_col):
        total_cases += 1
        actual_sequence = group[activity_col].dropna().astype(str).str.strip().tolist()

        if actual_sequence == happy_sequence:
            compliant_cases += 1

    compliance_rate = round((compliant_cases / total_cases) * 100, 2) if total_cases > 0 else 0.0

    result = {
        "happy_path_compliance_rate": compliance_rate,
        "total_cases": total_cases,
        "compliant_cases": compliant_cases,
        "non_compliant_cases": total_cases - compliant_cases,
        "happy_path_reference": " -> ".join(happy_sequence)
    }

    return json.dumps(result, indent=4)


import random




def simulate_actual_process(event_log_data, case_id_col, activity_col, start_col, end_col,
                            n_simulations=1000, variation=0.2):
    """
    Monte Carlo simulation based on ACTUAL paths in the event log.

    Each simulation randomly picks an existing real variant,
    then perturbs its activity durations by ±variation%.
    """

    df = pd.DataFrame(event_log_data)
    df[start_col] = pd.to_datetime(df[start_col], errors="coerce", utc=True)
    df[end_col] = pd.to_datetime(df[end_col], errors="coerce", utc=True)

    # Calculate actual durations
    df["duration_hr"] = (df[end_col] - df[start_col]).dt.total_seconds() / 3600

    # Average duration per activity
    avg_duration = df.groupby(activity_col)["duration_hr"].mean().to_dict()

    # --- Step 1: Build actual case paths (variants)
    case_paths = (
        df.groupby(case_id_col)[activity_col]
        .apply(list)
        .reset_index(name="path")
    )

    # Build list of unique paths with frequency
    path_counts = case_paths["path"].value_counts().reset_index()
    path_counts.columns = ["path", "count"]
    total_cases = len(case_paths)

    # Convert to list of (path, weight)
    variants = [(row["path"], row["count"] / total_cases) for _, row in path_counts.iterrows()]

    simulated_cases = []

    # --- Step 2: Run simulations
    for i in range(n_simulations):
        # Randomly select a variant (weighted by its frequency)
        variant, _ = random.choices(variants, weights=[w for _, w in variants])[0]

        total_time = 0.0
        total_cost = 0.0
        steps = []

        for act in variant:
            mean_dur = avg_duration.get(act, np.mean(list(avg_duration.values())))
            dur = random.uniform(mean_dur * (1 - variation), mean_dur * (1 + variation))
            cost = dur * 50  # $50/hr placeholder; can map actual costs later
            total_time += dur
            total_cost += cost
            steps.append({
                "activity": act,
                "sim_duration_hr": round(dur, 2),
                "sim_cost": round(cost, 2)
            })

        simulated_cases.append({
            "case_id": f"Sim_{i+1}",
            "total_time_hr": round(total_time, 2),
            "total_cost": round(total_cost, 2),
            "steps": steps
        })

    # --- Step 3: Aggregate results
    total_times = [c["total_time_hr"] for c in simulated_cases]
    total_costs = [c["total_cost"] for c in simulated_cases]

    result = {
        "simulation_type": "actual_path",
        "simulation_runs": n_simulations,
        "avg_cycle_time_hr": round(np.mean(total_times), 2),
        "min_cycle_time_hr": round(np.min(total_times), 2),
        "max_cycle_time_hr": round(np.max(total_times), 2),
        "avg_cost_per_case": round(np.mean(total_costs), 2),
        "variation_factor": variation,
        "sample_simulated_cases": simulated_cases[:5],
        "total_unique_variants": len(variants)
    }

    return json.dumps(result, indent=4)




def generate_visual_process_flow_data(project, event_log_data):
    """
    Generates frontend-friendly process efficiency data
    for graphical visualization (e.g. Sankey / flow diagram).
    """

    try:
        result_json = analyze_and_structure_process(event_log_data)
        result = json.loads(result_json)

        # 🔍 Debug check: what’s inside the result
        if isinstance(result, dict):
            process_nodes = result.get("process_flow_nodes", [])
        elif isinstance(result, list):
            # Sometimes older versions returned list directly
            process_nodes = result
        else:
            return json.dumps({"Error": "Unexpected data structure returned from analyzer."}, indent=4)

        if not process_nodes:
            print("⚠️ No process_flow_nodes found. Full result:", json.dumps(result, indent=2))
            return json.dumps([], indent=2)

        visual_data = []
        seen_ids = set()

        for node in process_nodes:
            node_id = str(node.get("id", ""))
            if not node_id or node_id in seen_ids:
                continue
            seen_ids.add(node_id)

            value_str = node.get("value", "0")
            try:
                value_float = float(value_str)
                value_str = f"{value_float:.2f}"
            except:
                value_str = "0.00"

            visual_entry = {
                "id": node_id,
                "label": node.get("label", "Unknown"),
                "value": value_str,
                "status": node.get("status", "in-progress"),
                "owner": node.get("owner", "Process Team"),
                "descriptions": node.get("descriptions", []),
                "isBottleneck": node.get("isBottleneck", False),
                "hasLoop": node.get("hasLoop", False),
                "isDropout": node.get("isDropout", False),
            }

            if node.get("loopConnections"):
                visual_entry["loopConnections"] = node["loopConnections"]

            extras = []
            if node.get("isBottleneck"):
                extras.append({
                    "id": f"{node_id}a",
                    "label": f"{node.get('label')} Review",
                    "position": "right"
                })
            if node.get("hasLoop"):
                extras.append({
                    "id": f"{node_id}b",
                    "label": f"{node.get('label')} Rework",
                    "position": "left",
                    "hasLoop": True,
                    "loopConnections": node.get("loopConnections", None)
                })

            visual_entry["extras"] = extras
            visual_data.append(visual_entry)

        return json.dumps(visual_data, indent=2)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({"Error": f"Failed to generate visual process flow: {e}"}, indent=4)