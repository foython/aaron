import pandas as pd
from datetime import timedelta
import json
import math
# class MockProject:
#     objects = None # Should be Project.objects
#     def __init__(self): self.user = None
#     def __call__(self, *args, **kwargs): return self 
# Project = MockProject
# DefineColumns = MockProject
# ProcessVariant = MockProject
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

def analyze_standard_path_performance_json(file_path):
 
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Error reading file: {e}")
        return [] # Return an empty list on failure

    df['timestamp_start'] = pd.to_datetime(df['timestamp_start'])
    df['timestamp_complete'] = pd.to_datetime(df['timestamp_complete'])
    df['duration'] = df['timestamp_complete'] - df['timestamp_start']

    df_paths = df.groupby('case_id')['activity'].apply(lambda x: ' -> '.join(x)).reset_index()
    df_variants = df_paths['activity'].value_counts().reset_index()
    
    # 💥 CRITICAL FIX: Ensure column names are set correctly 💥
    df_variants.columns = ['Process Path (Variant)', 'Frequency'] 
    
    most_standard_path_string = df_variants.sort_values(by='Frequency', ascending=False).iloc[0]['Process Path (Variant)']
    standard_path_activities = [a.strip() for a in most_standard_path_string.split('->')]

    df_avg_time = df.groupby('activity')['duration'].mean().reset_index()
    df_avg_time.rename(columns={'duration': 'Average Time (Duration)'}, inplace=True)

    df_filtered = df_avg_time[df_avg_time['activity'].isin(standard_path_activities)].copy()
    df_filtered['order'] = pd.Categorical(df_filtered['activity'], categories=standard_path_activities, ordered=True)
    df_result = df_filtered.sort_values('order').drop(columns=['order'])

    df_result['average_time_minutes'] = df_result['Average Time (Duration)'].dt.total_seconds() / 60

    df_result['serial_number'] = range(len(df_result))
    df_result.rename(columns={'activity': 'activity_name'}, inplace=True)

    df_final = df_result[['serial_number', 'activity_name', 'average_time_minutes']].copy()
    df_final['average_time_minutes'] = df_final['average_time_minutes'].round(2)

    json_output = df_final.to_dict('records')    
    
    return (json.dumps(json_output, indent=4))



import pandas as pd
import json
from datetime import timedelta
import numpy as np


def calculate_net_working_time(start_dt, end_dt, start_hour, end_hour):
    """
    Calculates the actual working time between two datetimes, respecting 
    specified daily work hours and skipping weekends (Saturday/Sunday).
    """
    total_seconds = 0
    current_dt = start_dt

    if start_dt >= end_dt:
        return 0

    while current_dt < end_dt:
        # Define work boundaries for the current day
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

# --- 2. Cycle Time Metrics Calculator with Date Filter (UNCHANGED) ---
def calculate_all_cycle_time_metrics(
    event_log_data,              # Event log data
    case_id_col,                 # 'case_id' column name
    start_time_col,              # 'timestamp_start' column name
    complete_time_col,           # 'timestamp_complete' column name
    office_start_hour=6,         # Project.start_hour
    office_end_hour=18,          # Project.end_hour
    time_unit='hours',
    start_date_filter=None,      # Optional start date for filtering (inclusive)
    end_date_filter=None         # Optional end date for filtering (exclusive)
):
    """
    Calculates key cycle time metrics using net working time.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
        
    try:        
        df = pd.DataFrame(event_log_data)
        required_cols = [case_id_col, start_time_col, complete_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)
    except Exception as e:
        return json.dumps({"Error": f"An error occurred during DataFrame creation: {e}"}, indent=4)

    df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
    df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

    if start_date_filter or end_date_filter:
        try:
            start_filter_dt = pd.to_datetime(start_date_filter, utc=True) if start_date_filter else pd.NaT
            end_filter_dt = pd.to_datetime(end_date_filter, utc=True) if end_date_filter else pd.NaT

            if pd.notna(start_filter_dt):
                df = df[df[start_time_col] >= start_filter_dt].copy()
            
            if pd.notna(end_filter_dt):
                df = df[df[complete_time_col] < end_filter_dt].copy()

        except Exception as e:
            print(f"Warning: Failed to parse date filter. Analysis proceeded without filtering. Error: {e}")
            
    if df.empty:
        return json.dumps({"Warning": "No data available for analysis after applying date filters."}, indent=4)

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
   
    unit_conversion = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'days': 86400}
    divisor = unit_conversion.get(time_unit.lower(), 3600)
    
    df_cycle_times['Adjusted_Cycle_Time'] = (
        df_cycle_times['Adjusted_Cycle_Time_Seconds'] / divisor
    )

    cycle_times = df_cycle_times['Adjusted_Cycle_Time'].values
    num_cases = len(cycle_times)
    
    if num_cases == 0:
        return json.dumps({"Error": "No cases found after grouping."}, indent=4)

    mean_time = np.mean(cycle_times)
    variance_time = np.var(cycle_times, ddof=0)
    std_dev_time = np.std(cycle_times, ddof=0)

    metrics = {
        "Total_Cases": num_cases,
        f"Average (Mean) Cycle Time ({time_unit})": round(mean_time, 2),
        f"Median Cycle Time ({time_unit})": round(np.median(cycle_times), 2),
        f"Minimum Cycle Time ({time_unit})": round(np.min(cycle_times), 2),
        f"Maximum Cycle Time ({time_unit})": round(np.max(cycle_times), 2),
        f"Variance ({time_unit}^2)": round(variance_time, 2),
        f"Standard Deviation ({time_unit})": round(std_dev_time, 2),
    }

    return json.dumps(metrics, indent=4)


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

        # 1. Convert Timestamps and Calculate Case Cycle Times
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()
        
        # Calculate net working time using the helper function
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

        # 2. Apply Date Filters (if provided)
        if start_date_filter:
            start_filter_dt = pd.to_datetime(start_date_filter, utc=True)
            df_cycle_times = df_cycle_times[df_cycle_times['Case_Start'] >= start_filter_dt].copy()
        
        if end_date_filter:
            end_filter_dt = pd.to_datetime(end_date_filter, utc=True)
            df_cycle_times = df_cycle_times[df_cycle_times['Case_End'] < end_filter_dt].copy()

        if df_cycle_times.empty:
            return json.dumps({"Warning": "No data available for analysis after filtering."}, indent=4)


        # 3. Determine Aggregation Grouping
        agg_level = aggregation_level.lower()
        
        if agg_level == 'week':
            # Group by ISO week (Monday-Sunday)
            df_cycle_times['Group_Period'] = df_cycle_times['Case_End'].dt.to_period('W').astype(str)
            period_name = 'week'
        elif agg_level == 'month':
            # Group by calendar month
            df_cycle_times['Group_Period'] = df_cycle_times['Case_End'].dt.to_period('M').astype(str)
            period_name = 'month'
        elif agg_level == 'all':
            # Group all data into one summary record
            df_cycle_times['Group_Period'] = 'All Time Summary'
            period_name = 'summary_period'
        else:
            return json.dumps({"Error": f"Invalid aggregation_level: '{aggregation_level}'. Must be 'week', 'month', or 'all'."}, indent=4)

        # 4. Aggregate Metrics
        period_metrics = df_cycle_times.groupby('Group_Period')['Cycle_Time_Days'].agg(
            Average_Cycle_Time=('mean'),
            Median_Cycle_Time=('median'),
            Total_Cases=('size')
        ).reset_index()

        # 5. Format Output
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
        
        # 1. Convert Timestamps
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        # 2. Determine Case End Times (Max complete time per case)
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cases = case_end.reset_index()

        # 3. Apply Date Filters (based on Case End Time)
        filtered_df = df_cases.copy()
        
        if start_date_filter:
            start_filter_dt = pd.to_datetime(start_date_filter, utc=True)
            # Filter cases that end on or after the start date
            filtered_df = filtered_df[filtered_df['Case_End'] >= start_filter_dt].copy()
        
        if end_date_filter:
            end_filter_dt = pd.to_datetime(end_date_filter, utc=True)
            # Filter cases that end before the end date (exclusive)
            filtered_df = filtered_df[filtered_df['Case_End'] < end_filter_dt].copy()

        # 4. Calculate final case count
        num_cases = filtered_df[case_id_col].nunique()

        result = {
            "Total_Unique_Cases": num_cases
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during case counting and filtering: {e}"}, indent=4)




def calculate_total_idle_time_metrics(
    event_log_data,
    case_id_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour
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

        df_cycle_times['Total_Cycle_Time_Seconds'] = (
            df_cycle_times['Case_End'] - df_cycle_times['Case_Start']
        ).dt.total_seconds()

        total_cycle_time_seconds = df_cycle_times['Total_Cycle_Time_Seconds'].sum()

        df_cycle_times['Adjusted_Cycle_Time_Seconds'] = df_cycle_times.apply(
            lambda row: calculate_net_working_time(
                row['Case_Start'], 
                row['Case_End'], 
                office_start_hour, 
                office_end_hour
            ), 
            axis=1
        )

        total_working_time_seconds = df_cycle_times['Adjusted_Cycle_Time_Seconds'].sum()

        total_idle_time_seconds = total_cycle_time_seconds - total_working_time_seconds
  
        idle_time_ratio = (total_idle_time_seconds / total_cycle_time_seconds) if total_cycle_time_seconds > 0 else 0.0

        total_idle_time_hours = total_idle_time_seconds / 3600

        result = {
            "Total_Idle_Time_Hours": round(total_idle_time_hours, 2),
            "Idle_Time_Ratio_Percentage": round(idle_time_ratio * 100, 2),
            "Total_Cycle_Time_Seconds": total_cycle_time_seconds,
            "Total_Working_Time_Seconds": total_working_time_seconds
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during idle time calculation: {e}"}, indent=4)
    


def calculate_loop_metrics(event_log_data, case_id_col, activity_col):   
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)
     
        total_steps = len(df)

        case_metrics = df.groupby(case_id_col).agg(
            Total_Events_Per_Case=(case_id_col, 'count'),
            Unique_Activities_Per_Case=(activity_col, 'nunique')
        ).reset_index()

        case_metrics['Loops_Per_Case'] = (
            case_metrics['Total_Events_Per_Case'] - case_metrics['Unique_Activities_Per_Case']
        )

        total_loops = case_metrics['Loops_Per_Case'].sum()

        loop_ratio = (total_loops / total_steps) if total_steps > 0 else 0.0

        result = {
            "Total_Loops": int(total_loops),
            "Total_Process_Steps": int(total_steps),
            "Loops_Ratio_Percentage": round(loop_ratio * 100, 2),
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during loop calculation: {e}"}, indent=4)
    




def calculate_bottleneck_metrics(
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

        df['Processing_Time_Seconds'] = (
            df[complete_time_col] - df[start_time_col]
        ).dt.total_seconds()
        
 
        avg_processing_time_summary = df.groupby(activity_col)['Processing_Time_Seconds'].mean().reset_index()

        avg_processing_time_summary = avg_processing_time_summary.rename(
            columns={'Processing_Time_Seconds': 'Average_Time_Seconds'}
        )
   
        avg_processing_time_summary['Average_Time_Hours'] = (
            avg_processing_time_summary['Average_Time_Seconds'] / 3600
        ).round(2)

        activity_avg_times = avg_processing_time_summary.set_index(activity_col)['Average_Time_Hours'].to_dict()


        df_analysis = pd.merge(df, avg_processing_time_summary[[activity_col, 'Average_Time_Seconds']], on=activity_col, how='left')

        df_analysis['Deviation_Seconds'] = df_analysis['Processing_Time_Seconds'] - df_analysis['Average_Time_Seconds']

        df_analysis['Excess_Time_Seconds'] = df_analysis['Deviation_Seconds'].apply(lambda x: max(0, x))

        total_time_lost_seconds = df_analysis['Excess_Time_Seconds'].sum()

        bottleneck_metrics = {
            "Bottleneck_Activity": "N/A",
            "Bottleneck_Case_ID": "N/A",
            "Max_Excess_Time_Hours": 0.0,
            "Total_Time_Lost_Hours": 0.0,
            "Bottleneck_Ratio_Percentage": 0.0,
        }

        if total_time_lost_seconds > 0:

            max_bottleneck_row = df_analysis.loc[
                df_analysis['Excess_Time_Seconds'].idxmax()
            ]

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

            bottleneck_metrics = {
                "Bottleneck_Activity": max_bottleneck_row[activity_col],
                "Bottleneck_Case_ID": max_bottleneck_row[case_id_col],
                "Max_Excess_Time_Hours": round(max_bottleneck_row['Excess_Time_Seconds'] / 3600, 2),
                "Total_Time_Lost_Hours": round(total_time_lost_seconds / 3600, 2),
                "Bottleneck_Ratio_Percentage": round(bottleneck_ratio * 100, 2),
            }

        
        result = {
            "Activity_Average_Processing_Time_Hours": activity_avg_times,
            "Largest_Bottleneck_Metrics": bottleneck_metrics,
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during bottleneck calculation: {e}"}, indent=4)
    



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

        df_sorted = df.sort_values(by=complete_time_col, ascending=False)

        last_events = df_sorted.groupby(case_id_col).first().reset_index()


        total_cases = last_events[case_id_col].nunique()

        if total_cases == 0:
             return json.dumps({
                "Dropout_Rate_Percentage": 0.0,
                "Number_of_Dropout_Cases": 0,
                "Total_Cases": 0,
                "Expected_Final_Activity_Derived": "N/A"
            }, indent=4)

        activity_counts = last_events[activity_col].value_counts()
        most_common_final_activity = activity_counts.index[0]
        cases_ending_with_expected = int(activity_counts.iloc[0])

        dropout_cases = last_events[
            last_events[activity_col] != most_common_final_activity
        ]
        num_dropout_cases = len(dropout_cases)

        dropout_rate = (num_dropout_cases / total_cases) 

        result = {
            "Dropout_Rate_Percentage": round(dropout_rate * 100, 2),
            "Number_of_Dropout_Cases": int(num_dropout_cases),
            "Total_Cases": int(total_cases),
            "Expected_Final_Activity_Derived": most_common_final_activity,
            "Cases_Ending_With_Expected_Activity": cases_ending_with_expected
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during dropout rate calculation: {e}"}, indent=4)
    




def calculate_average_activity_duration(
    event_log_data,
    activity_col,
    start_time_col,
    complete_time_col
):
    """Calculates the average processing time for each activity in the event log."""

    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        # ... (Validation checks omitted for brevity but remain important) ...
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        df['Processing_Time_Seconds'] = (
            df[complete_time_col] - df[start_time_col]
        ).dt.total_seconds()

        avg_processing_time_summary = df.groupby(activity_col)['Processing_Time_Seconds'].mean().reset_index()

        avg_processing_time_summary['Average_Time_Hours'] = (
            avg_processing_time_summary['Processing_Time_Seconds'] / 3600
        ).round(2)

        activity_avg_times = avg_processing_time_summary.set_index(activity_col)['Average_Time_Hours'].to_dict()

        result = {
            "Average_Activity_Duration_Hours": activity_avg_times
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
            "Variant_Complexity_Index": round(variant_complexity_index, 4), # Ratio (0.0 to 1.0)
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




def calculate_total_completed_cases(event_log_data, case_id_col):   
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        if case_id_col not in df.columns:
             return json.dumps({"Error": f"Missing required column in data: {case_id_col}"}, indent=4)

        total_cases = df[case_id_col].nunique()

        result = {
            "KPI_Name": "Total Completed Cases",
            "Value": int(total_cases)
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during case count calculation: {e}"}, indent=4)
    


def calculate_happy_path_deviation(
    event_log_data, 
    case_id_col, 
    activity_col, 
    start_time_col,
    complete_time_col, 
    happy_path_data
):
    """
    Calculates the average deviation (in steps and time) of non-compliant cases
    from the defined Happy Path.
    
    Time deviation benchmark: Minimum cycle time of compliant cases.
    Step deviation benchmark: Happy Path length.
    
    Also provides data for a bar chart showing activities causing deviation.
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






def calculate_case_throughput_rate(
    event_log_data, 
    case_id_col, 
    complete_time_col, 
    period='D' # 'D' for Day, 'W' for Week, 'M' for Month
):
    """
    Calculates the Case Throughput Rate (number of completed cases per time unit)
    and provides data for line chart visualization.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    if period not in ['D', 'W', 'M']:
        return json.dumps({"Error": "Period must be 'D' (Day), 'W' (Week), or 'M' (Month)."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, complete_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        df_case_completion = (
            df.groupby(case_id_col)[complete_time_col]
            .max()
            .reset_index(name='Case_End') 
        )
        
        total_cases = len(df_case_completion)
        if total_cases == 0:
            return json.dumps({"Total_Cases_Completed": 0, "Throughput_Rate_Per_Period": 0.0}, indent=4)

        pd_resample_period = period
        date_format = "%Y-%m-%d"
        period_unit_text = "day"

        if period == 'W':            
            period_unit_text = "week"
            date_format = "%Y-W%W"
        elif period == 'M':
            
            pd_resample_period = 'ME'
            period_unit_text = "month"
            date_format = "%Y-%m" 

        min_completion_date = df_case_completion['Case_End'].min().date()
        max_completion_date = df_case_completion['Case_End'].max().date()
        total_days_span = (max_completion_date - min_completion_date).days + 1

        if period == 'W':
            total_time_units = max(1, math.ceil(total_days_span / 7))
        elif period == 'M':
            start_month = min_completion_date.year * 12 + min_completion_date.month
            end_month = max_completion_date.year * 12 + max_completion_date.month
            total_time_units = max(1, end_month - start_month + 1)
        else: 
            total_time_units = total_days_span

        throughput_rate = total_cases / total_time_units if total_time_units > 0 else 0.0

        df_case_completion = df_case_completion.set_index('Case_End')

        cases_per_period = df_case_completion.resample(pd_resample_period)[case_id_col].count().rename('Cases_Completed')
        
        line_chart_data = []
        for timestamp, count in cases_per_period.items():
            if period == 'W':
                 formatted_period = timestamp.to_period('W-MON').start_time.strftime(date_format)
            else:
                 formatted_period = timestamp.strftime(date_format)
                 
            line_chart_data.append({
                "period": formatted_period,
                "count": int(count)
            })

        
        result = {
            "Total_Cases_Completed": int(total_cases),
            
            "Throughput_Rate_Per_Period": round(throughput_rate, 2),
            "Rate_Period_Unit": period_unit_text,

            "Throughput_Distribution": line_chart_data
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during throughput rate calculation: {e}"}, indent=4)   


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


def analyze_and_structure_process_data(
    event_log_data, 
    case_id_col='case_id', 
    activity_col='activity_name', 
    start_time_col='start_time', 
    complete_time_col='complete_time',
    bottleneck_top_n=3 # This parameter is now deprecated, using overall average instead
):
   
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)

        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        df['Event_Duration_Seconds'] = (
            df[complete_time_col] - df[start_time_col]
        ).dt.total_seconds()
        
        df['duration'] = df[complete_time_col] - df[start_time_col]
        overall_avg_duration = df['duration'].mean()

        case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()
        
        df_cycle_times['Cycle_Time_Seconds'] = (
            df_cycle_times['Case_End'] - df_cycle_times['Case_Start']
        ).dt.total_seconds()
        
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

        df_paths = df.groupby(case_id_col)[activity_col].apply(lambda x: ' -> '.join(x)).reset_index(name='Process Path (Variant)')
        df_variants = df_paths['Process Path (Variant)'].value_counts().reset_index()
        most_standard_path_string = df_variants.sort_values(by='count', ascending=False).iloc[0]['Process Path (Variant)']
        standard_activities = [a.strip() for a in most_standard_path_string.split('->')]

        all_activities_df = pd.DataFrame(df[activity_col].unique(), columns=['label'])
        all_activities_df['id'] = (all_activities_df.index + 1).astype(str)
        activity_to_id_map = all_activities_df.set_index('label')['id'].to_dict()
        
        df['Next Activity'] = df.groupby(case_id_col)[activity_col].shift(-1)
        df_transitions = df.dropna(subset=['Next Activity']).copy()

        df_dfg = df_transitions.groupby([activity_col, 'Next Activity']).size().reset_index(name='count')
        df_dfg.columns = ['Source', 'Target', 'Frequency']
        
        df_activity_counts = df.groupby([case_id_col, activity_col]).size().reset_index(name='count')
        rework_activities = set(df_activity_counts[df_activity_counts['count'] > 1][activity_col].unique())

        df_avg_time_raw = df.groupby(activity_col).agg(
            avg_duration=('duration', 'mean'),
            total_count=(activity_col, 'size')
        ).reset_index()
        
        df_avg_time_raw['hasLoop'] = df_avg_time_raw[activity_col].apply(lambda x: x in rework_activities)
        df_avg_time_raw['isBottleneck'] = df_avg_time_raw['avg_duration'] > overall_avg_duration

        df_last_activities = df.groupby(case_id_col)[activity_col].last()
        expected_end_activity = df_last_activities.mode().iloc[0] 
        dropout_counts = df_last_activities[df_last_activities != expected_end_activity].value_counts()
        major_dropout_points = set(dropout_counts.index[:5]) 
        df_avg_time_raw['isDropout'] = df_avg_time_raw[activity_col].apply(lambda x: x in major_dropout_points)


        def get_loop_connections(row):
            activity = row['label']
            if not row['hasLoop']: 
                return None

            current_id = activity_to_id_map.get(activity)
            if current_id is None:
                return None

            df_outbound = df_dfg[df_dfg['Source'] == activity].sort_values(by='Frequency', ascending=False)
            valid_backward_targets = {}
  
            for _, transition in df_outbound.iterrows():
                target = transition['Target']
                target_id = activity_to_id_map.get(target)

                if target_id is None:
                    continue

                if target == activity:
                    return {"from": current_id, "to": target_id}

                if int(target_id) < int(current_id):
                     valid_backward_targets[target_id] = transition['Frequency']

            if valid_backward_targets:
                best_target_id = max(valid_backward_targets.keys(), key=int)
                return {"from": current_id, "to": best_target_id}

            if not df_outbound.empty:
                most_frequent_transition = df_outbound.iloc[0]
                target = most_frequent_transition['Target']
                target_id = activity_to_id_map.get(target)
                
                if target_id is not None and target_id != current_id:
                    return {"from": current_id, "to": target_id}

            return None


        df_master = pd.DataFrame(standard_activities, columns=['label'])
        df_master = df_master.merge(df_avg_time_raw, left_on='label', right_on=activity_col, how='left')
        
        df_ids_to_merge = all_activities_df[['label', 'id']].rename(columns={'id': 'activity_id'})
        df_master = df_master.merge(df_ids_to_merge, on='label', how='left')
        
        df_master['id'] = df_master['activity_id']
        df_master['value'] = df_master['avg_duration'].dt.total_seconds().fillna(0) / 60
        df_master['value'] = df_master['value'].round(2).astype(str)

        df_master['loopConnections'] = df_master.apply(
            lambda row: get_loop_connections({'label': row['label'], 'hasLoop': row['hasLoop']}), 
            axis=1
        )

        df_master['status'] = np.where(df_master['label'] == expected_end_activity, 'final', 'in-progress')
        df_master['owner'] = "N/A" 
        df_master['descriptions'] = df_master.apply(
            lambda row: [
                f"Activity occurs {int(row['total_count'])} times." if pd.notna(row['total_count']) else "Activity count: 0.",

                f"Average processing time: {seconds_to_dhms(row['avg_duration'].total_seconds() if pd.notna(row['avg_duration']) else 0)}"
            ], 
            axis=1
        )

        cols_to_drop = [activity_col, 'avg_duration', 'total_count', 'activity_id']
        df_master.drop(columns=cols_to_drop, inplace=True, errors='ignore')
        
        final_cols = ['id', 'label', 'value', 'status', 'owner', 'descriptions', 'isBottleneck', 'hasLoop', 'isDropout', 'loopConnections', 'extras']

        process_flow_nodes = df_master.rename(columns={'label': 'label'}).replace({np.nan: None, None: None}).to_dict('records')

        for node in process_flow_nodes:
            node['owner'] = node.get('owner', 'N/A')
            node['extras'] = node.get('extras', [])


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
                    "Activities_In_Loops_Count": len(rework_activities),
                    "Time_Lost_Simplified_Basis": "Loop/Rework analysis is now embedded in 'process_flow_nodes' loopConnections.",
                },
                
                "Bottleneck_Analysis_Simplified": {
                    "Bottlenecks_Based_on_Avg_Duration_Count": len(df_master[df_master['isBottleneck']]),
                    "Time_Lost_Simplified_Basis": "Bottlenecks flagged if avg duration > overall log avg duration.",
                }
            },
            
            "process_flow_nodes": process_flow_nodes
        }
        
        return json.dumps(final_output, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during process analysis: {e}"}, indent=4)




import pandas as pd
import json
import numpy as np
import math
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

# --- MAIN COMPREHENSIVE ANALYSIS FUNCTION ---

def analyze_and_structure_process_datas(
    event_log_data, 
    case_id_col='case_id', 
    activity_col='activity_name', 
    start_time_col='start_time', 
    complete_time_col='complete_time',
    bottleneck_top_n=3 # This parameter is now deprecated, using overall average instead
):
    """
    Calculates key process mining metrics and structures the output into a global
    metrics summary and an annotated process flow node list, based on the Most 
    Frequent Path and enhanced loop detection logic.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        # 1. Prepare Data and Calculate Event/Case Durations
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
        
        # Calculate the duration of each activity event (processing time)
        df['Event_Duration_Seconds'] = (
            df[complete_time_col] - df[start_time_col]
        ).dt.total_seconds()
        
        df['duration'] = df[complete_time_col] - df[start_time_col]
        overall_avg_duration = df['duration'].mean()

        # Calculate case cycle times (Required for global metrics)
        case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()
        
        df_cycle_times['Cycle_Time_Seconds'] = (
            df_cycle_times['Case_End'] - df_cycle_times['Case_Start']
        ).dt.total_seconds()
        
        # --- 2. Calculate GLOBAL METRICS ---
        
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
        
        # --- 3. Determine Actual Path and Activity-Level Metrics (ENHANCED LOGIC) ---
        
        # 3a. Determine Most Frequent Path
        df_paths = df.groupby(case_id_col)[activity_col].apply(lambda x: ' -> '.join(x)).reset_index(name='Process Path (Variant)')
        df_variants = df_paths['Process Path (Variant)'].value_counts().reset_index()
        most_standard_path_string = df_variants.sort_values(by='count', ascending=False).iloc[0]['Process Path (Variant)']
        standard_activities = [a.strip() for a in most_standard_path_string.split('->')]

        # 3b. Create master list of all unique activities and assign IDs
        all_activities_df = pd.DataFrame(df[activity_col].unique(), columns=['label'])
        all_activities_df['id'] = (all_activities_df.index + 1).astype(str)
        activity_to_id_map = all_activities_df.set_index('label')['id'].to_dict()
        
        # 3c. Calculate DFG and Rework flags
        df['Next Activity'] = df.groupby(case_id_col)[activity_col].shift(-1)
        df_transitions = df.dropna(subset=['Next Activity']).copy()

        df_dfg = df_transitions.groupby([activity_col, 'Next Activity']).size().reset_index(name='count')
        df_dfg.columns = ['Source', 'Target', 'Frequency']
        
        df_activity_counts = df.groupby([case_id_col, activity_col]).size().reset_index(name='count')
        rework_activities = set(df_activity_counts[df_activity_counts['count'] > 1][activity_col].unique())

        df_avg_time_raw = df.groupby(activity_col).agg(
            avg_duration=('duration', 'mean'),
            total_count=(activity_col, 'size')
        ).reset_index()
        
        df_avg_time_raw['hasLoop'] = df_avg_time_raw[activity_col].apply(lambda x: x in rework_activities)
        df_avg_time_raw['isBottleneck'] = df_avg_time_raw['avg_duration'] > overall_avg_duration

        # 3d. Dropout identification
        df_last_activities = df.groupby(case_id_col)[activity_col].last()
        expected_end_activity = df_last_activities.mode().iloc[0] 
        dropout_counts = df_last_activities[df_last_activities != expected_end_activity].value_counts()
        major_dropout_points = set(dropout_counts.index[:5]) 
        df_avg_time_raw['isDropout'] = df_avg_time_raw[activity_col].apply(lambda x: x in major_dropout_points)


        # --- 4. Loop Connection Logic ---
        
        # Define the connection logic based on the DFG
        def get_loop_connections(row):
            activity = row['label']
            if not row['hasLoop']: 
                return None

            current_id = activity_to_id_map.get(activity)
            if current_id is None:
                return None

            df_outbound = df_dfg[df_dfg['Source'] == activity].sort_values(by='Frequency', ascending=False)
            valid_backward_targets = {}
            
            # PHASE 1: FIND BACKWARD LOOPS (Highest Priority)
            for _, transition in df_outbound.iterrows():
                target = transition['Target']
                target_id = activity_to_id_map.get(target)

                if target_id is None:
                    continue

                # 1. Self-loop (Highest Priority)
                if target == activity:
                    return {"from": current_id, "to": target_id}
                
                # 2. Backward loop (Target ID < Current ID)
                if int(target_id) < int(current_id):
                     valid_backward_targets[target_id] = transition['Frequency']
            
            # Return the shortest backward loop (MAXIMUM valid target ID) if found
            if valid_backward_targets:
                best_target_id = max(valid_backward_targets.keys(), key=int)
                return {"from": current_id, "to": best_target_id}

            # PHASE 2: FALLBACK TO FORWARD SKIP
            if not df_outbound.empty:
                most_frequent_transition = df_outbound.iloc[0]
                target = most_frequent_transition['Target']
                target_id = activity_to_id_map.get(target)
                
                if target_id is not None and target_id != current_id:
                    return {"from": current_id, "to": target_id}

            return None


        # --- 5. Structure Output: Process Flow Nodes (Filtered to Standard Path) ---
        
        # Merge metrics and IDs into a master DataFrame filtered by the standard path
        df_master = pd.DataFrame(standard_activities, columns=['label'])
        df_master = df_master.merge(df_avg_time_raw, left_on='label', right_on=activity_col, how='left')
        
        df_ids_to_merge = all_activities_df[['label', 'id']].rename(columns={'id': 'activity_id'})
        df_master = df_master.merge(df_ids_to_merge, on='label', how='left')
        
        df_master['id'] = df_master['activity_id']
        # Convert Timedelta to float (seconds/minutes), operating on the Series level which is safer
        df_master['value'] = df_master['avg_duration'].dt.total_seconds().fillna(0) / 60
        df_master['value'] = df_master['value'].round(2).astype(str)
        
        # Apply the new loop connection logic
        df_master['loopConnections'] = df_master.apply(
            lambda row: get_loop_connections({'label': row['label'], 'hasLoop': row['hasLoop']}), 
            axis=1
        )

        # Set final node properties
        df_master['status'] = np.where(df_master['label'] == expected_end_activity, 'final', 'in-progress')
        df_master['owner'] = "N/A" # Resource information requires another column
        
        # Safely extract total_seconds() using pd.notna() to prevent Timedelta errors
        df_master['descriptions'] = df_master.apply(
            lambda row: [
                # Safely handle total_count (which might be NaN if an activity is in the path but missing from log)
                f"Activity occurs {int(row['total_count'])} times." if pd.notna(row['total_count']) else "Activity count: 0.",
                
                # Use conditional logic to check if avg_duration is a valid Timedelta before calling .total_seconds()
                f"Average processing time: {seconds_to_dhms(row['avg_duration'].total_seconds() if pd.notna(row['avg_duration']) else 0)}"
            ], 
            axis=1
        )
        
        # Dropping the original columns that contain Timedelta ('avg_duration') or are redundant
        cols_to_drop = [activity_col, 'avg_duration', 'total_count', 'activity_id']
        df_master.drop(columns=cols_to_drop, inplace=True, errors='ignore')
        
        final_cols = ['id', 'label', 'value', 'status', 'owner', 'descriptions', 'isBottleneck', 'hasLoop', 'isDropout', 'loopConnections', 'extras']
        
        # Filter to required columns and convert
        process_flow_nodes = df_master.rename(columns={'label': 'label'}).replace({np.nan: None, None: None}).to_dict('records')

        # Ensure all required keys exist and handle None values for lists/dicts
        for node in process_flow_nodes:
            # Set default values for missing keys in the new structure
            node['owner'] = node.get('owner', 'N/A')
            node['extras'] = node.get('extras', [])
            
        
        # --- 6. Final JSON Output ---

        final_output = {
            "global_metrics": {
                "Total_Completed_Cases": int(total_cases),
                "Case_Throughput_Rate_Per_Day": round(throughput_rate, 2),
                "Max_Steps_in_a_Case": int(max_steps_count),
                "Most_Frequent_Path": most_standard_path_string, # Added for context
                
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
                    "Activities_In_Loops_Count": len(rework_activities),
                    "Time_Lost_Simplified_Basis": "Loop/Rework analysis is now embedded in 'process_flow_nodes' loopConnections.",
                },
                
                "Bottleneck_Analysis_Simplified": {
                    "Bottlenecks_Based_on_Avg_Duration_Count": len(df_master[df_master['isBottleneck']]),
                    "Time_Lost_Simplified_Basis": "Bottlenecks flagged if avg duration > overall log avg duration.",
                }
            },
            
            "process_flow_nodes": process_flow_nodes
        }
        
        return json.dumps(final_output, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during process analysis: {e}"}, indent=4)
    


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

# --- Internal Single Log Analyzer (Core Logic Reuse for comparison) ---




# --- NEW FUNCTION FOR PATH-BASED KPI BENCHMARKING (Single Log) ---

def analyze_path_kpi_benchmarks(
    event_log_data,
    case_id_col='case_id',
    activity_col='activity_name',
    start_time_col='start_time',
    complete_time_col='complete_time'
):
    """
    Calculates the most frequent path and returns an ordered table of activities 
    along that path, including average processing time and process problem flags 
    (Loop, Bottleneck, Dropout).
    
    The output also includes a summary of the total counts for Loop, Bottleneck, 
    and Dropout activities found in that path.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        # 1. Data Preparation
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
        df['duration'] = df[complete_time_col] - df[start_time_col]
        
        # Calculate overall average activity duration for bottleneck threshold
        overall_avg_duration = df['duration'].mean()

        # 2. Most Frequent Path Identification
        df_paths = df.groupby(case_id_col)[activity_col].apply(lambda x: ' -> '.join(x)).reset_index(name='Process Path')
        df_variants = df_paths['Process Path'].value_counts().reset_index()
        df_variants.columns = ['Process Path', 'Frequency'] 
        most_standard_path_string = df_variants.sort_values(by='Frequency', ascending=False).iloc[0]['Process Path']
        standard_activities = [a.strip() for a in most_standard_path_string.split('->')]

        # 3. Problem Flag Calculation

        # A. Rework/Loop (Activity appears > 1 time in a case)
        df_activity_counts = df.groupby([case_id_col, activity_col]).size().reset_index(name='count')
        rework_activities = set(df_activity_counts[df_activity_counts['count'] > 1][activity_col].unique())

        # B. Dropout (Non-final activity that frequently ends the case)
        df_last_activities = df.groupby(case_id_col)[activity_col].last()
        expected_end_activity = df_last_activities.mode().iloc[0] 
        # Identify top 5 activities that are NOT the expected end activity but appear as the last activity
        dropout_counts = df_last_activities[df_last_activities != expected_end_activity].value_counts()
        major_dropout_points = set(dropout_counts.index[:5]) 

        # 4. Activity Metrics and Merging
        df_metrics = df.groupby(activity_col)['duration'].mean().reset_index()
        df_metrics.rename(columns={'duration': 'avg_duration'}, inplace=True)
        df_metrics['average_time_minutes'] = df_metrics['avg_duration'].dt.total_seconds() / 60
        df_metrics.drop(columns=['avg_duration'], inplace=True)
        
        # C. Bottleneck (Avg time > Overall Avg time)
        overall_avg_time_minutes = overall_avg_duration.total_seconds() / 60
        df_metrics['is_bottleneck'] = df_metrics['average_time_minutes'] > overall_avg_time_minutes

        # Merge problem flags
        df_metrics['is_loop'] = df_metrics[activity_col].apply(lambda x: x in rework_activities)
        df_metrics['is_dropout'] = df_metrics[activity_col].apply(lambda x: x in major_dropout_points)

        # 5. Filter and Order by Most Frequent Path
        df_path_kpi = df_metrics[df_metrics[activity_col].isin(standard_activities)].copy()
        
        df_path_kpi['order'] = pd.Categorical(df_path_kpi[activity_col], categories=standard_activities, ordered=True)
        df_path_kpi = df_path_kpi.sort_values('order').drop(columns=['order'])
        
        df_path_kpi['serial_number'] = range(1, len(df_path_kpi) + 1)
        df_path_kpi.rename(columns={activity_col: 'activity_name'}, inplace=True)
        df_path_kpi['average_time_minutes'] = df_path_kpi['average_time_minutes'].round(2)

        # 6. Final Structure (Path Activities)
        json_output = df_path_kpi[[
            'serial_number', 
            'activity_name', 
            'average_time_minutes', 
            'is_loop', 
            'is_bottleneck', 
            'is_dropout'
        ]].to_dict('records')
        
        # 7. Calculate overall summary counts for the path
        loop_count = int(df_path_kpi['is_loop'].sum())
        bottleneck_count = int(df_path_kpi['is_bottleneck'].sum())
        dropout_count = int(df_path_kpi['is_dropout'].sum())

        return json.dumps({
            "most_frequent_path": most_standard_path_string,
            "path_kpi_summary": {
                "total_activities_in_path": len(standard_activities),
                "total_loop_activities": loop_count,
                "total_bottleneck_activities": bottleneck_count,
                "total_dropout_activities": dropout_count
            },
            "path_kpi_benchmark_table": json_output
        }, indent=4)

    except Exception as e:
        import traceback
        return json.dumps({"Error": f"An error occurred during path KPI analysis: {e}", "Traceback": traceback.format_exc()}, indent=4)




def calculate_kpi_summary(event_log_data, case_id_col, activity_col, timestamp_start, timestamp_end, office_start_hour, office_end_hour):
    """
    Calculates a comprehensive set of process KPIs including cycle times, steps, loops, and bottlenecks 
    using the entire event log data (no date filtering applied).
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        # 1. Data Preparation
        df[timestamp_start] = pd.to_datetime(df[timestamp_start], utc=True)
        df[timestamp_end] = pd.to_datetime(df[timestamp_end], utc=True)
        
        # Sort log by case ID and start time for sequence-dependent metrics (loops, bottlenecks)
        df = df.sort_values(by=[case_id_col, timestamp_start]).reset_index(drop=True)

        # Determine Case Start/End Times (for Cycle Time)
        case_start = df.groupby(case_id_col)[timestamp_start].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[timestamp_end].max().rename('Case_End')
        df_cases = pd.merge(case_start, case_end, on=case_id_col).reset_index()
        
        # --- Base Metrics ---
        total_cases = df_cases[case_id_col].nunique()
        completed_cases = total_cases # Assuming all cases that exist in df_cases are completed

        if total_cases == 0:
            return json.dumps({"Warning": "No cases found in the event log."}, indent=4)

        dropout_rate = 0.0

        # --- Cycle Time Metrics ---
        
        df_cases['Adjusted_Cycle_Time_Seconds'] = df_cases.apply(
            lambda row: calculate_net_working_time(
                row['Case_Start'], 
                row['Case_End'], 
                office_start_hour, 
                office_end_hour
            ), 
            axis=1
        )
        
        # Convert cycle time to Hours
        df_cases['Adjusted_Cycle_Time_Hours'] = df_cases['Adjusted_Cycle_Time_Seconds'] / 3600.0

        median_cycle_time_h = df_cases['Adjusted_Cycle_Time_Hours'].median()
        average_cycle_time_h = df_cases['Adjusted_Cycle_Time_Hours'].mean()
        variance_cycle_time_h2 = df_cases['Adjusted_Cycle_Time_Hours'].var()
        dev_cycle_time_h = df_cases['Adjusted_Cycle_Time_Hours'].std()
        min_cycle_time_h = df_cases['Adjusted_Cycle_Time_Hours'].min()
        max_cycle_time_h = df_cases['Adjusted_Cycle_Time_Hours'].max()

        # --- Steps/Case Metrics ---
        
        steps_per_case = df.groupby(case_id_col).size()
        median_steps = steps_per_case.median()
        average_steps = steps_per_case.mean()

        # --- Loops/Rework Metrics ---
        
        # Identify cases where the same activity appears more than once (rework/loop)
        looped_cases_df = df.groupby(case_id_col)[activity_col].apply(lambda x: x.duplicated().any())
        total_loops_cases = looped_cases_df.sum()
        
        loops_ratio = (total_loops_cases / total_cases) * 100

        # --- Bottleneck Analysis (Idle Time between activities) ---
        
        # 1. Calculate the time difference between the current activity's end and the next activity's start
        df['Next_Start'] = df.groupby(case_id_col)[timestamp_start].shift(-1)
        df['Idle_Time_Seconds'] = (df['Next_Start'] - df[timestamp_end]).dt.total_seconds()
        
        # Filter out NaN (last event in case) and negative times 
        df_idle = df[df['Idle_Time_Seconds'].notna() & (df['Idle_Time_Seconds'] >= 0)].copy()

        # 2. Group idle time by the activity *preceding* the wait
        # This identifies WHICH activity causes the wait for the NEXT one.
        idle_time_by_activity = df_idle.groupby(activity_col)['Idle_Time_Seconds'].mean()
        
        if idle_time_by_activity.empty:
             largest_bottleneck = "N/A"
             bottleneck_severity_min = 0.0
        else:
            # Convert to minutes for severity reporting
            idle_time_by_activity_min = idle_time_by_activity / 60.0
            
            # Find the activity with the maximum average idle time (The overall largest)
            largest_bottleneck = idle_time_by_activity_min.idxmax()
            bottleneck_severity_min = idle_time_by_activity_min.max()

        # 3. Handle specific requested bottlenecks (Payment Monitoring and Receipt Reconciled)
        # .get() will return 0.0 if the activity name isn't found in the log
        payment_monitoring_severity = idle_time_by_activity_min.get('Payment Monitoring', 0.0)
        receipt_reconciled_severity = idle_time_by_activity_min.get('Receipt Reconciled', 0.0)


        # --- Final Results Packaging ---
        
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
            # Key 1: The overall largest (dynamic) bottleneck
            "Largest_Bottleneck_Activity": largest_bottleneck,
            "Bottleneck_Severity_min": round(bottleneck_severity_min, 2),
            # Key 2 & 3: Specific requested bottlenecks
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
    """
    Filter the event log using Date and Variant filters, and then apply 
    Cycle Time filters by calculating the case cycle time on-the-fly.
    """
    filtered_df = df.copy()
    try:
        filtered_df[timestamp_start_col] = pd.to_datetime(
            filtered_df[timestamp_start_col], errors='coerce'
        )
        # Ensure the completion timestamp column is also converted
        filtered_df[timestamp_complete_col] = pd.to_datetime(
            filtered_df[timestamp_complete_col], errors='coerce'
        )
    except KeyError as e:
        # Provide a clearer error if expected columns are missing
        raise ValueError(f"Missing timestamp column in CSV: {e}")
    except Exception as e:
        # Handle cases where conversion fails (e.g., unexpected data types)
        raise ValueError(f"Error converting timestamps to datetime: {e}")

    # --- 1. Pre-processing: Ensure Timestamps are in datetime format ---
    filtered_df[timestamp_start_col] = pd.to_datetime(filtered_df[timestamp_start_col])
    
    # --- 2. Date Filter (based on case START time) ---
    # Case start times are calculated BEFORE filtering to avoid issues with partial cases
    case_start_times = filtered_df.groupby(case_id_col)[timestamp_start_col].min().reset_index()
    
    if start_date:
        start_dt = pd.to_datetime(start_date)
        valid_cases = case_start_times[case_start_times[timestamp_start_col] >= start_dt][case_id_col]
        filtered_df = filtered_df[filtered_df[case_id_col].isin(valid_cases)]
        
    if end_date:
        end_dt = pd.to_datetime(end_date)
        valid_cases = case_start_times[case_start_times[timestamp_start_col] <= end_dt][case_id_col]
        # Filter the DataFrame based on cases that passed the date filter
        filtered_df = filtered_df[filtered_df[case_id_col].isin(valid_cases)]

    if selected_variants and len(selected_variants) > 0:
        
        # 1. Calculate the Variant Path for all cases in the *currently filtered* log (after date filter)
        # Group by case ID and aggregate the activity names into a list
        case_activities = filtered_df.groupby(case_id_col)[variant_col].apply(list).reset_index(name='activities')

        # Convert the list of activities into the variant path string
        case_activities['calculated_variant_path'] = case_activities['activities'].apply(
            lambda x: ' -> '.join(x)
        )
        
        # 2. Standardize and Clean for filtering (Crucial for string matching)
        
        # Clean the calculated paths
        clean_calculated_paths = case_activities['calculated_variant_path'].str.lower().str.strip()
        
        # Clean the input filter list (the paths from the database)
        clean_selected_variants = [v.lower().strip() for v in selected_variants]

        # 3. Identify the Case IDs that match the selected variant paths
        
        # Find the indices of the matching paths in the temporary table
        matching_indices = clean_calculated_paths.isin(clean_selected_variants)
        
        # Extract the unique Case IDs corresponding to these matches
        matching_case_ids = case_activities[matching_indices][case_id_col].unique()

        # 4. Filter the main event log (filtered_df) using these Case IDs
        filtered_df = filtered_df[filtered_df[case_id_col].isin(matching_case_ids)]
    # --- 4. Cycle Time Filter (Calculated on-the-fly) ---
    # ... (Step 4 remains the same as it correctly operates on the case_id_col) ...
    if min_cycle_time is not None or max_cycle_time is not None:
        
        if filtered_df.empty:
             return filtered_df
             
        # Calculate Case Start Time (min) and Case End Time (max)
        case_times = filtered_df.groupby(case_id_col).agg(
            case_start=(timestamp_start_col, 'min'),
            case_end=(timestamp_complete_col, 'max')
        ).reset_index()
        
        # ⭐️ CRITICAL FIX: Ensure final aggregated columns are datetime just before subtraction ⭐️
        # This double-checks the aggregation result, preventing the ndarray error.
        case_times['case_start'] = pd.to_datetime(case_times['case_start'])
        case_times['case_end'] = pd.to_datetime(case_times['case_end'])
        
        # Calculate Cycle Time (Time Delta)
        # This subtraction (case_end - case_start) will now correctly produce a Timedelta object.
        case_times['cycle_time_delta'] = case_times['case_end'] - case_times['case_start']
        
        # ... (rest of the cycle time conversion and filtering logic remains the same) ...
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
