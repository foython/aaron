import pandas as pd
from datetime import timedelta
import json
import math

def analyze_standard_path_performance_json(file_path):
    # 1. Load the data (assuming CSV, adjust sep if needed)
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Error reading file: {e}")
        return [] # Return an empty list on failure

    # --- INITIAL DATA PROCESSING ---
    df['timestamp_start'] = pd.to_datetime(df['timestamp_start'])
    df['timestamp_complete'] = pd.to_datetime(df['timestamp_complete'])
    df['duration'] = df['timestamp_complete'] - df['timestamp_start']

    # --- STEP 1: Programmatically Determine the Most Standard Path ---
    df_paths = df.groupby('case_id')['activity'].apply(lambda x: ' -> '.join(x)).reset_index()
    df_variants = df_paths['activity'].value_counts().reset_index()
    
    # 💥 CRITICAL FIX: Ensure column names are set correctly 💥
    df_variants.columns = ['Process Path (Variant)', 'Frequency'] 
    
    most_standard_path_string = df_variants.sort_values(by='Frequency', ascending=False).iloc[0]['Process Path (Variant)']
    standard_path_activities = [a.strip() for a in most_standard_path_string.split('->')]


    # --- STEP 2: Calculate Average Time for ONLY those activities in that sequence ---
    
    # Calculate the master average duration for all unique activities
    df_avg_time = df.groupby('activity')['duration'].mean().reset_index()
    df_avg_time.rename(columns={'duration': 'Average Time (Duration)'}, inplace=True)

    # Filter for activities in the standard path and sort by sequence
    df_filtered = df_avg_time[df_avg_time['activity'].isin(standard_path_activities)].copy()
    df_filtered['order'] = pd.Categorical(df_filtered['activity'], categories=standard_path_activities, ordered=True)
    df_result = df_filtered.sort_values('order').drop(columns=['order'])

    # --- STEP 3: Format the Output as Requested ---
    
    # Convert timedelta to total minutes
    df_result['average_time_minutes'] = df_result['Average Time (Duration)'].dt.total_seconds() / 60
    
    # Create the final columns
    df_result['serial_number'] = range(len(df_result))
    df_result.rename(columns={'activity': 'activity_name'}, inplace=True)

    # Select and format the final columns
    df_final = df_result[['serial_number', 'activity_name', 'average_time_minutes']].copy()
    df_final['average_time_minutes'] = df_final['average_time_minutes'].round(2)
    
    # Convert to a list of dictionaries (JSON-like format)
    json_output = df_final.to_dict('records')    
    
    return (json.dumps(json_output, indent=4))

# --- Example Usage (Assuming your file is named '0.csv') ---
# analyze_standard_path_performance_json('0.csv')


import pandas as pd
import numpy as np
from datetime import timedelta
import json
import os

# --- CORE BUSINESS HOURS CALCULATION FUNCTION (UNCHANGED) ---
def calculate_net_working_time(start_dt, end_dt, start_hour, end_hour):
    """Calculates seconds between two datetimes, excluding non-working hours."""
    # ... (function body remains the same) ...
    total_seconds = 0
    current_dt = start_dt

    if start_dt >= end_dt:
        return 0

    while current_dt < end_dt:
        # Define working hours block for the current day using project-specific hours
        work_day_start = current_dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        work_day_end = current_dt.replace(hour=end_hour, minute=0, second=0, microsecond=0)

        # 1. Skip to the start of the next working day if current_dt is on a weekend or after end_hour
        if current_dt.weekday() not in [0, 1, 2, 3, 4] or current_dt >= work_day_end:
            current_dt += timedelta(days=1)
            while current_dt.weekday() not in [0, 1, 2, 3, 4]:
                current_dt += timedelta(days=1)
            current_dt = current_dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            continue

        # 2. Skip non-working hours (before start_hour)
        if current_dt < work_day_start:
            current_dt = work_day_start
            continue

        # 3. Calculate time spent within the current working hour block
        effective_start = current_dt
        effective_end = min(end_dt, work_day_end)

        if effective_end > effective_start:
            total_seconds += (effective_end - effective_start).total_seconds()
        
        # 4. Advance current_dt
        if effective_end == end_dt:
            break
        
        current_dt = effective_end 

    return total_seconds


# --- REFACTORED MAIN METRICS CALCULATION FUNCTION (UNCHANGED) ---
def calculate_all_cycle_time_metrics_from_model(
    event_log_data,              # Event log data (list of dictionaries/QuerySet values)
    case_id_col,                 # 'case_id' column name
    start_time_col,              # 'timestamp_start' column name
    complete_time_col,           # 'timestamp_complete' column name
    office_start_hour=6,         # Project.start_hour (e.g., 6)
    office_end_hour=18,          # Project.end_hour (e.g., 18)
    time_unit='hours'
):
    """
    Calculates all cycle time metrics using data and configurable office hours.
    """
    
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
        
    try:
        # 1. Load Data from Model Data (list of dicts)
        # This line is correct for Django, but requires a list of dicts.
        df = pd.DataFrame(event_log_data)
        
        # Ensure column names exist
        required_cols = [case_id_col, start_time_col, complete_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

    except Exception as e:
        # Catch and return error as JSON
        return json.dumps({"Error": f"An error occurred during DataFrame creation: {e}"}, indent=4)

    # ... (Rest of the function logic remains the same) ...

    # 2. Prepare Data and Determine Case Boundaries
    df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
    df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

    case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
    case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
    df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()

    # 3. Calculate Adjusted Cycle Time (Seconds) - USING PARAMETER HOURS
    df_cycle_times['Adjusted_Cycle_Time_Seconds'] = df_cycle_times.apply(
        lambda row: calculate_net_working_time(
            row['Case_Start'], 
            row['Case_End'], 
            office_start_hour, 
            office_end_hour
        ), 
        axis=1
    )
    
    # 4. Convert to the requested unit
    unit_conversion = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'days': 86400}
    divisor = unit_conversion.get(time_unit, 3600)
    
    df_cycle_times['Adjusted_Cycle_Time'] = (
        df_cycle_times['Adjusted_Cycle_Time_Seconds'] / divisor
    )

    # 5. Calculate ALL Metrics
    cycle_times = df_cycle_times['Adjusted_Cycle_Time'].values
    num_cases = len(cycle_times)
    
    if num_cases == 0:
        return json.dumps({"Error": "No cases found after grouping."}, indent=4)

    mean_time = np.mean(cycle_times)
    variance_time = np.var(cycle_times, ddof=0)
    
    metrics = {
        "Total_Cases": num_cases,
        f"Average (Mean) Cycle Time ({time_unit})": round(mean_time, 2),
        f"Median Cycle Time ({time_unit})": round(np.median(cycle_times), 2),
        f"Minimum Cycle Time ({time_unit})": round(np.min(cycle_times), 2),
        f"Maximum Cycle Time ({time_unit})": round(np.max(cycle_times), 2),
        f"Variance ({time_unit}^2)": round(variance_time, 2),
        f"Standard Deviation ({time_unit})": round(np.std(cycle_times, ddof=0), 2),
    }

    return json.dumps(metrics, indent=4)




import pandas as pd
import numpy as np
from datetime import timedelta
import json
import os

# --- HARDCODED GLOBAL CONFIGURATION ---
WORKING_DAYS = [0, 1, 2, 3, 4] # Monday=0 to Friday=4

# --- CORE BUSINESS HOURS CALCULATION FUNCTION ---

def calculate_net_working_time(start_dt, end_dt, start_hour, end_hour):
    """
    Calculates seconds between two datetimes, excluding non-working hours 
    (weekends and time outside start_hour-end_hour).
    """
    total_seconds = 0
    current_dt = start_dt

    if start_dt >= end_dt:
        return 0

    while current_dt < end_dt:
        # Define working hours block for the current day using project-specific hours
        work_day_start = current_dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        work_day_end = current_dt.replace(hour=end_hour, minute=0, second=0, microsecond=0)

        # 1. Skip to the start of the next working day if current_dt is on a weekend or after end_hour
        if current_dt.weekday() not in WORKING_DAYS or current_dt >= work_day_end:
            current_dt += timedelta(days=1)
            while current_dt.weekday() not in WORKING_DAYS:
                current_dt += timedelta(days=1)
            current_dt = current_dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            continue

        # 2. Skip non-working hours (before start_hour)
        if current_dt < work_day_start:
            current_dt = work_day_start
            continue

        # 3. Calculate time spent within the current working hour block
        effective_start = current_dt
        effective_end = min(end_dt, work_day_end)

        if effective_end > effective_start:
            total_seconds += (effective_end - effective_start).total_seconds()
        
        # 4. Advance current_dt
        if effective_end == end_dt:
            break
        
        current_dt = effective_end 

    return total_seconds


# --- MAIN FUNCTION TO GENERATE MONTHLY DATA TABLE ---

def create_monthly_cycle_time_data(
    event_log_data,
    case_id_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour
):
    """
    Calculates and returns the mean and median cycle time for every month in the log 
    as a JSON string (list of dictionaries).
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)

        # 1. Prepare Data and Determine Case Boundaries
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()

        # 2. Calculate Adjusted Cycle Time (Seconds)
        df_cycle_times['Adjusted_Cycle_Time_Seconds'] = df_cycle_times.apply(
            lambda row: calculate_net_working_time(
                row['Case_Start'], 
                row['Case_End'], 
                office_start_hour, 
                office_end_hour
            ), 
            axis=1
        )
        
        # 3. Convert Cycle Time to Days
        df_cycle_times['Cycle_Time_Days'] = df_cycle_times['Adjusted_Cycle_Time_Seconds'] / 86400.0

        # 4. Group by Month of Completion and calculate metrics
        df_cycle_times['Completion_Month'] = df_cycle_times['Case_End'].dt.to_period('M')

        monthly_metrics = df_cycle_times.groupby('Completion_Month')['Cycle_Time_Days'].agg(
            Average_Cycle_Time=('mean'),
            Median_Cycle_Time=('median')
        ).reset_index()

        # 5. Format Output
        monthly_metrics['Completion_Month'] = monthly_metrics['Completion_Month'].astype(str)
        monthly_metrics['Average_Cycle_Time'] = monthly_metrics['Average_Cycle_Time'].round(2)
        monthly_metrics['Median_Cycle_Time'] = monthly_metrics['Median_Cycle_Time'].round(2)

        # Convert the DataFrame to a list of dictionaries (records) and then to a JSON string
        data_records = monthly_metrics.rename(columns={
            'Completion_Month': 'month', 
            'Average_Cycle_Time': 'average_cycle_time_days',
            'Median_Cycle_Time': 'median_cycle_time_days'
        }).to_dict('records')
        
        return json.dumps(data_records, indent=4)
    
    except Exception as e:
        # Catch exceptions during processing and return an error JSON
        return json.dumps({"Error": f"An error occurred during monthly data processing: {e}"}, indent=4)
    


def calculate_total_cases(event_log_data, case_id_col):
    """
    Calculates the total number of unique cases in the event log data.

    Args:
        event_log_data (list of dicts): The event log data (simulating a Django QuerySet values list).
        case_id_col (str): The name of the column that uniquely identifies a case (e.g., 'case_id').

    Returns:
        str: A JSON string containing the total number of unique cases, or an error message.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
        
    try:
        # 1. Load data from the list of dictionaries
        df = pd.DataFrame(event_log_data)
        
        # 2. Check if the required column exists
        if case_id_col not in df.columns:
             return json.dumps({"Error": f"Missing required column: '{case_id_col}'"}, indent=4)

        # 3. Calculate the number of unique cases
        num_cases = df[case_id_col].nunique()
        
        # 4. Format and return the result as a JSON string
        result = {
            "Total_Unique_Cases": num_cases
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during case counting: {e}"}, indent=4)
    



def calculate_total_idle_time_metrics(
    event_log_data,
    case_id_col,
    start_time_col,
    complete_time_col,
    office_start_hour,
    office_end_hour
):
    """
    Calculates the aggregate Total Idle Time and Idle Time Ratio across all cases.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, start_time_col, complete_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        # 1. Prepare Data and Determine Case Boundaries
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()

        # 2. Calculate Total Cycle Time (Wall Time Seconds)
        df_cycle_times['Total_Cycle_Time_Seconds'] = (
            df_cycle_times['Case_End'] - df_cycle_times['Case_Start']
        ).dt.total_seconds()
        
        # Aggregate Total Cycle Time (Sum across all cases)
        total_cycle_time_seconds = df_cycle_times['Total_Cycle_Time_Seconds'].sum()

        # 3. Calculate Total Working Time (Adjusted Time Seconds)
        df_cycle_times['Adjusted_Cycle_Time_Seconds'] = df_cycle_times.apply(
            lambda row: calculate_net_working_time(
                row['Case_Start'], 
                row['Case_End'], 
                office_start_hour, 
                office_end_hour
            ), 
            axis=1
        )
        
        # Aggregate Total Working Time (Sum across all cases)
        total_working_time_seconds = df_cycle_times['Adjusted_Cycle_Time_Seconds'].sum()
        
        # 4. Calculate Idle Time
        total_idle_time_seconds = total_cycle_time_seconds - total_working_time_seconds
        
        # 5. Calculate Idle Time Ratio
        idle_time_ratio = (total_idle_time_seconds / total_cycle_time_seconds) if total_cycle_time_seconds > 0 else 0.0

        # 6. Format Output
        
        # Convert total seconds to hours for a user-friendly KPI number
        total_idle_time_hours = total_idle_time_seconds / 3600

        result = {
            "Total_Idle_Time_Hours": round(total_idle_time_hours, 2),
            "Idle_Time_Ratio_Percentage": round(idle_time_ratio * 100, 2),
            # Include seconds for raw data accuracy, although the primary KPI is hours/ratio
            "Total_Cycle_Time_Seconds": total_cycle_time_seconds,
            "Total_Working_Time_Seconds": total_working_time_seconds
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during idle time calculation: {e}"}, indent=4)
    


def calculate_loop_metrics(event_log_data, case_id_col, activity_col):
    """
    Calculates the aggregate Total Loops and Loop Ratio (rework ratio) across the process.
    Loop Count for a case = Total Events - Unique Activities.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)
        
        # 1. Calculate Total Process Steps (Total Events)
        total_steps = len(df)
        
        # 2. Calculate Total Events and Unique Activities per Case
        case_metrics = df.groupby(case_id_col).agg(
            Total_Events_Per_Case=(case_id_col, 'count'),
            Unique_Activities_Per_Case=(activity_col, 'nunique')
        ).reset_index()
        
        # 3. Calculate Loops per Case
        # Loop = Total Events - Unique Activities. This counts events that are repeats.
        case_metrics['Loops_Per_Case'] = (
            case_metrics['Total_Events_Per_Case'] - case_metrics['Unique_Activities_Per_Case']
        )
        
        # 4. Aggregate Total Loops
        total_loops = case_metrics['Loops_Per_Case'].sum()
        
        # 5. Calculate Loop Ratio
        loop_ratio = (total_loops / total_steps) if total_steps > 0 else 0.0

        # 6. Format Output
        
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
    """
    Calculates the Average Processing Time for each activity, and identifies the 
    largest Bottleneck based on *excess processing time deviation* from the activity average.
    """
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
        
        # --- PART 1: Calculate Average Processing Time for Each Activity ---
        
        # 1.1 Calculate the duration of each event (Processing Time)
        df['Processing_Time_Seconds'] = (
            df[complete_time_col] - df[start_time_col]
        ).dt.total_seconds()
        
        # 1.2 Group by activity and calculate the mean processing time
        avg_processing_time_summary = df.groupby(activity_col)['Processing_Time_Seconds'].mean().reset_index()
        
        # Rename column for clarity before merging
        avg_processing_time_summary = avg_processing_time_summary.rename(
            columns={'Processing_Time_Seconds': 'Average_Time_Seconds'}
        )
        
        # 1.3 Convert average time to hours and format output
        avg_processing_time_summary['Average_Time_Hours'] = (
            avg_processing_time_summary['Average_Time_Seconds'] / 3600
        ).round(2)
        
        # Format for output dictionary (Activity Name: Average Time in Hours)
        activity_avg_times = avg_processing_time_summary.set_index(activity_col)['Average_Time_Hours'].to_dict()


        # --- PART 2: Identify Bottleneck Based on Processing Time Deviation ---
        
        # 2.1 Merge average time back into the main DataFrame
        df_analysis = pd.merge(df, avg_processing_time_summary[[activity_col, 'Average_Time_Seconds']], on=activity_col, how='left')

        # 2.2 Calculate Excess Time (Positive Deviation from Average) for each event
        df_analysis['Deviation_Seconds'] = df_analysis['Processing_Time_Seconds'] - df_analysis['Average_Time_Seconds']
        
        # Excess Time is only the time that exceeds the average (time lost due to bottleneck)
        df_analysis['Excess_Time_Seconds'] = df_analysis['Deviation_Seconds'].apply(lambda x: max(0, x))

        # 2.3 Calculate Total Time Lost to Bottlenecks (sum of all excess time)
        total_time_lost_seconds = df_analysis['Excess_Time_Seconds'].sum()

        # 2.4 Identify the Single Largest Bottleneck Event (for reporting)
        bottleneck_metrics = {
            "Bottleneck_Activity": "N/A",
            "Bottleneck_Case_ID": "N/A",
            "Max_Excess_Time_Hours": 0.0,
            "Total_Time_Lost_Hours": 0.0,
            "Bottleneck_Ratio_Percentage": 0.0,
        }

        if total_time_lost_seconds > 0:
            # Find the row with the maximum excess time
            max_bottleneck_row = df_analysis.loc[
                df_analysis['Excess_Time_Seconds'].idxmax()
            ]
            
            # 2.5 Calculate Total Process Wall Time
            case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
            case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
            df_case_duration = pd.merge(case_start, case_end, on=case_id_col).reset_index()

            df_case_duration['Total_Cycle_Time_Seconds'] = (
                df_case_duration['Case_End'] - df_case_duration['Case_Start']
            ).dt.total_seconds()
            
            total_process_wall_time_seconds = df_case_duration['Total_Cycle_Time_Seconds'].sum()

            # 2.6 Calculate Bottleneck Ratio (Total Excess Time / Total Process Wall Time)
            bottleneck_ratio = (
                total_time_lost_seconds / total_process_wall_time_seconds
            ) if total_process_wall_time_seconds > 0 else 0.0
            
            # 2.7 Format Bottleneck Output
            bottleneck_metrics = {
                "Bottleneck_Activity": max_bottleneck_row[activity_col],
                "Bottleneck_Case_ID": max_bottleneck_row[case_id_col],
                "Max_Excess_Time_Hours": round(max_bottleneck_row['Excess_Time_Seconds'] / 3600, 2),
                "Total_Time_Lost_Hours": round(total_time_lost_seconds / 3600, 2),
                "Bottleneck_Ratio_Percentage": round(bottleneck_ratio * 100, 2),
            }


        # --- PART 3: Combine and Return ---
        
        result = {
            "Activity_Average_Processing_Time_Hours": activity_avg_times,
            "Largest_Bottleneck_Metrics": bottleneck_metrics,
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during bottleneck calculation: {e}"}, indent=4)
    



def calculate_steps_per_case_metrics(event_log_data, case_id_col):
    """
    Calculates the Median and Average (Mean) number of steps (events) per case.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        if case_id_col not in df.columns:
             return json.dumps({"Error": f"Missing required column in data: {case_id_col}"}, indent=4)

        # 1. Count steps (events) for each case
        steps_per_case = df.groupby(case_id_col).size().rename('Steps_Count')
        
        if steps_per_case.empty:
            return json.dumps({
                "Average_Steps_Per_Case": 0.0,
                "Median_Steps_Per_Case": 0.0
            }, indent=4)

        # 2. Calculate average (mean) steps
        average_steps = steps_per_case.mean()
        
        # 3. Calculate median steps
        median_steps = steps_per_case.median()

        # 4. Format Output
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
    """
    Calculates the Dropout Rate by automatically determining the 'Expected Final Activity' 
    (the activity that ends the majority of cases) and calculating the percentage of cases 
    that did not reach this activity.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, complete_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)
        
        # Ensure time column is datetime for correct sorting
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        # 1. Sort by completion time to reliably find the last event in each case
        df_sorted = df.sort_values(by=complete_time_col, ascending=False)
        
        # 2. Get the latest event (row) for each case
        last_events = df_sorted.groupby(case_id_col).first().reset_index()

        # 3. Count total cases
        total_cases = last_events[case_id_col].nunique()

        if total_cases == 0:
             return json.dumps({
                "Dropout_Rate_Percentage": 0.0,
                "Number_of_Dropout_Cases": 0,
                "Total_Cases": 0,
                "Expected_Final_Activity_Derived": "N/A"
            }, indent=4)

        # 4. Determine the Most Common Final Activity (the derived 'Happy Path' end)
        activity_counts = last_events[activity_col].value_counts()
        most_common_final_activity = activity_counts.index[0]
        cases_ending_with_expected = int(activity_counts.iloc[0])

        # 5. Identify dropout cases
        # A case is a dropout if its last activity is NOT the derived most common activity
        dropout_cases = last_events[
            last_events[activity_col] != most_common_final_activity
        ]
        num_dropout_cases = len(dropout_cases)

        # 6. Calculate dropout rate
        dropout_rate = (num_dropout_cases / total_cases) 
        
        # 7. Format Output
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
    """
    Calculates the average duration (processing time) for each distinct activity 
    in the event log.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)

        required_cols = [activity_col, start_time_col, complete_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        # 1. Calculate the duration (Processing Time) for each event
        df['Processing_Time_Seconds'] = (
            df[complete_time_col] - df[start_time_col]
        ).dt.total_seconds()

        # 2. Group by activity and calculate the mean processing time
        avg_processing_time_summary = df.groupby(activity_col)['Processing_Time_Seconds'].mean().reset_index()

        # 3. Convert average time to hours and format output
        avg_processing_time_summary['Average_Time_Hours'] = (
            avg_processing_time_summary['Processing_Time_Seconds'] / 3600
        ).round(2)

        # Format for output dictionary (Activity Name: Average Time in Hours)
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
    """
    Calculates the total number of unique process variants (traces) in the event log,
    and identifies the most frequent variant and its frequency, providing a count-focused output.
    
    A variant is the unique sequence of activities from case start to end.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        # Only require the columns needed to define the trace/variant
        required_cols = [case_id_col, activity_col, complete_time_col] 
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
        
        # 1. Sort events within each case by completion time to determine the correct sequence (trace)
        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])

        # 2. Group by case ID and aggregate the activity column into an ordered list
        case_traces = df_sorted.groupby(case_id_col)[activity_col].apply(list).reset_index()

        # 3. Convert the activity list into a variant string (e.g., 'A -> B -> C')
        case_traces['Variant'] = case_traces[activity_col].apply(lambda x: ' -> '.join(x))
        
        # 4. Count the frequency of each unique variant
        variant_counts = case_traces['Variant'].value_counts()
        
        # 5. Extract metrics
        total_unique_variants = len(variant_counts)
        total_cases = len(case_traces)
        
        most_frequent_variant = "N/A"
        most_frequent_count = 0
        
        if not variant_counts.empty:
            most_frequent_variant = variant_counts.index[0]
            most_frequent_count = int(variant_counts.iloc[0])
        
        most_frequent_percentage = (most_frequent_count / total_cases) * 100 if total_cases > 0 else 0.0

        # 6. Format Output (Simplified)
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
    top_n=5 # Default to Top 5
):
    """
    Calculates and returns the Top N most frequent process variants (traces) 
    with their absolute counts and percentage shares.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, complete_time_col] 
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
        
        # 1. Sort events within each case by completion time to determine the correct sequence (trace)
        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])

        # 2. Group by case ID and aggregate the activity column into an ordered list
        case_traces = df_sorted.groupby(case_id_col)[activity_col].apply(list).reset_index()

        # 3. Convert the activity list into a variant string (e.g., 'A -> B -> C')
        case_traces['Variant'] = case_traces[activity_col].apply(lambda x: ' -> '.join(x))
        
        # 4. Count the frequency of each unique variant (Sorted Descending by Count)
        variant_counts = case_traces['Variant'].value_counts()
        total_cases = len(case_traces)
        
        # 5. Extract Top N variants
        top_variants_data = []

        # Iterate over the top N items in the sorted variant counts
        for variant, count in variant_counts.head(top_n).items():
            percentage = (count / total_cases) * 100 if total_cases > 0 else 0.0
            
            top_variants_data.append({
                "Variant_Trace": variant,
                "Count": int(count),
                "Percentage": round(percentage, 2)
            })
            
        # 6. Format Output
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
    """
    Calculates the First Pass Rate (FPR), which is the percentage of cases 
    that complete the process without any loops or rework.
    A case is 'First Pass' if the total number of events equals the number 
    of unique activities.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        # 1. Calculate Total Events and Unique Activities per Case
        case_metrics = df.groupby(case_id_col).agg(
            Total_Events_Per_Case=(case_id_col, 'count'),
            Unique_Activities_Per_Case=(activity_col, 'nunique')
        ).reset_index()
        
        # 2. Identify First Pass cases
        # A case is First Pass if Total Events == Unique Activities (i.e., Loops = 0)
        case_metrics['Is_First_Pass'] = (
            case_metrics['Total_Events_Per_Case'] == case_metrics['Unique_Activities_Per_Case']
        )
        
        # 3. Aggregate results
        total_cases = len(case_metrics)
        first_pass_cases = case_metrics['Is_First_Pass'].sum()
        
        # 4. Calculate Rate
        first_pass_rate = (first_pass_cases / total_cases) * 100 if total_cases > 0 else 0.0

        # 5. Format Output
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
    """
    Calculates the activity pair (A -> B) with the longest AVERAGE waiting time.
    Waiting time = B_start_time - A_complete_time.
    """
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

        # 1. Sort the log by case ID and completion time to define the flow sequence
        df_sorted = df.sort_values(by=[case_id_col, complete_time_col]).reset_index(drop=True)
        
        # 2. Identify the subsequent event's start time and activity using shift()
        # This operation is grouped by case ID to ensure the shift only happens within the same case
        df_sorted['Next_Activity'] = df_sorted.groupby(case_id_col)[activity_col].shift(-1)
        df_sorted['Next_Start_Time'] = df_sorted.groupby(case_id_col)[start_time_col].shift(-1)

        # 3. Filter out the last event of each case (where Next_Activity is NaN)
        df_transitions = df_sorted.dropna(subset=['Next_Activity']).copy()

        # 4. Calculate Waiting Time
        # Waiting Time = Next Activity Start Time - Current Activity Complete Time
        df_transitions['Waiting_Time_Seconds'] = (
            df_transitions['Next_Start_Time'] - df_transitions[complete_time_col]
        ).dt.total_seconds()
        
        # Filter out negative waiting times (should not happen with good data, but prevents errors)
        df_transitions = df_transitions[df_transitions['Waiting_Time_Seconds'] >= 0]
        
        # 5. Group by transition pair (Current Activity -> Next Activity) and calculate the average
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

        # 6. Identify the longest average waiting time step
        longest_wait_step = transition_metrics.loc[
            transition_metrics['Average_Waiting_Time_Seconds'].idxmax()
        ]

        # 7. Format Output
        
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
    """
    Calculates the Variant Complexity Index (VCI), which is the ratio of 
    the total number of unique process variants to the total number of cases.
    VCI = Total Unique Variants / Total Cases
    A VCI closer to 1.0 indicates high diversity/low standardization.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, complete_time_col] 
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
        
        # 1. Sort events within each case by completion time to determine the correct sequence (trace)
        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])

        # 2. Group by case ID and aggregate the activity column into an ordered list (the trace)
        case_traces = df_sorted.groupby(case_id_col)[activity_col].apply(list).reset_index()

        # 3. Convert the activity list into a variant string for easy counting
        case_traces['Variant'] = case_traces[activity_col].apply(lambda x: ' -> '.join(x))
        
        # 4. Count the frequency of each unique variant
        variant_counts = case_traces['Variant'].value_counts()
        
        # 5. Extract metrics
        total_unique_variants = len(variant_counts)
        total_cases = len(case_traces)
        
        # 6. Calculate VCI
        variant_complexity_index = (
            total_unique_variants / total_cases
        ) if total_cases > 0 else 0.0

        # 7. Format Output
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
    """
    Calculates the trend of unique process variant counts over specified time periods.
    This shows how process diversity (complexity) changes over time.
    """
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
        
        # 1. Determine the trace/variant for every case
        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])
        case_traces = df_sorted.groupby(case_id_col).agg(
            Variant=(activity_col, lambda x: ' -> '.join(x)),
            Case_End_Time=(complete_time_col, 'max') # Use the last event's completion time to anchor the case
        ).reset_index()

        # 2. Group cases by the specified time period
        # Use pandas PeriodIndex for grouping and consistent time labels
        case_traces['Time_Period'] = case_traces['Case_End_Time'].dt.to_period(time_period.upper())
        
        # 3. Calculate metrics for each period
        # Count the number of unique variants and the total number of cases completed
        time_trend = case_traces.groupby('Time_Period').agg(
            Unique_Variant_Count=('Variant', 'nunique'),
            Total_Cases_Completed=('case_id', 'count')
        ).reset_index()

        # 4. Calculate the Variant Complexity Index (VCI) per period
        time_trend['Variant_Complexity_Index'] = (
            time_trend['Unique_Variant_Count'] / time_trend['Total_Cases_Completed']
        )
        
        # 5. Format Output
        
        # Convert PeriodIndex object to a readable string
        time_trend['Time_Period_Label'] = time_trend['Time_Period'].astype(str)
        
        # Structure the final output list
        time_trend_list = time_trend[[
            'Time_Period_Label', 
            'Unique_Variant_Count', 
            'Total_Cases_Completed', 
            'Variant_Complexity_Index'
        ]].to_dict('records')
        
        # Apply rounding to the VCI
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
    """
    Calculates the percentage of all cases that followed the single most frequent 
    process variant (the 'top' or 'happy' path).
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, complete_time_col] 
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
        
        # 1. Sort events within each case by completion time to determine the correct sequence (trace)
        df_sorted = df.sort_values(by=[case_id_col, complete_time_col])

        # 2. Group by case ID and aggregate the activity column into an ordered list
        case_traces = df_sorted.groupby(case_id_col)[activity_col].apply(list).reset_index()

        # 3. Convert the activity list into a variant string (e.g., 'A -> B -> C')
        case_traces['Variant'] = case_traces[activity_col].apply(lambda x: ' -> '.join(x))
        
        # 4. Count the frequency of each unique variant
        variant_counts = case_traces['Variant'].value_counts()
        
        # 5. Extract metrics
        total_cases = len(case_traces)
        most_frequent_count = 0
        most_frequent_variant = "N/A"
        
        if not variant_counts.empty:
            most_frequent_count = int(variant_counts.iloc[0])
            most_frequent_variant = variant_counts.index[0]
        
        # 6. Calculate the percentage of cases following the top variant
        top_variant_percentage = (most_frequent_count / total_cases) * 100 if total_cases > 0 else 0.0

        # 7. Format Output
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
    """
    Calculates the maximum number of steps (events/activities) found in any single case.
    This helps identify process outliers and highly complex cases.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        if case_id_col not in df.columns:
             return json.dumps({"Error": f"Missing required column in data: {case_id_col}"}, indent=4)

        # 1. Count steps (events) for each case
        steps_per_case = df.groupby(case_id_col).size().rename('Steps_Count')
        
        if steps_per_case.empty:
            return json.dumps({
                "Max_Steps_Count": 0,
                "Case_ID_With_Max_Steps": "N/A"
            }, indent=4)

        # 2. Find the maximum step count
        max_steps = int(steps_per_case.max())
        
        # 3. Find the Case ID(s) corresponding to the maximum step count
        case_id_with_max_steps = steps_per_case[steps_per_case == max_steps].index.tolist()

        # 4. Format Output
        result = {
            "Max_Steps_Count": max_steps,
            # Return only the first ID if multiple cases tie for the max
            "Case_ID_With_Max_Steps": case_id_with_max_steps[0] if case_id_with_max_steps else "N/A",
            "Cases_Tied_for_Max": len(case_id_with_max_steps)
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during max steps calculation: {e}"}, indent=4)


def seconds_to_dhms(seconds):
    """Converts a total number of seconds into a days, hours, minutes, seconds string."""
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
    if seconds > 0 or not parts: # Include seconds if less than a minute, or if the time is 0
        parts.append(f"{round(seconds, 2)}s")

    return sign + " ".join(parts)



def calculate_time_saved_potential(
    event_log_data, 
    case_id_col, 
    start_time_col, 
    complete_time_col
):
    """
    Calculates the Average Time Saved Potential. This is the difference between 
    the average case cycle time and the fastest (minimum) case cycle time.
    
    Potential Saved Time = Mean Cycle Time - Minimum Cycle Time (Fastest Case).
    """
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

        # 1. Determine Case Boundaries (Start and End)
        case_start = df.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()

        # 2. Calculate Cycle Time (Total Throughput Time) for Each Case in Seconds
        df_cycle_times['Cycle_Time_Seconds'] = (
            df_cycle_times['Case_End'] - df_cycle_times['Case_Start']
        ).dt.total_seconds()
        
        if df_cycle_times.empty:
            return json.dumps({"Error": "No valid cases found for cycle time calculation."}, indent=4)

        # 3. Calculate Mean (T_avg) and Minimum (T_min) Cycle Times
        mean_cycle_time_seconds = df_cycle_times['Cycle_Time_Seconds'].mean()
        min_cycle_time_seconds = df_cycle_times['Cycle_Time_Seconds'].min()
        total_cases = len(df_cycle_times)

        # 4. Calculate Average Time Saved Potential
        avg_time_saved_potential_seconds = max(0, mean_cycle_time_seconds - min_cycle_time_seconds)
        
        # 5. Calculate Total Time Saved Potential (Total Cases * Avg Potential)
        total_time_saved_potential_seconds = avg_time_saved_potential_seconds * total_cases

        # 6. Format Output
        
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
    """
    Calculates the frequency distribution of activities in the event log.
    Returns the absolute count and percentage for each activity, sorted by count.
    
    The output is structured for easy visualization (e.g., a horizontal bar chart).
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        if activity_col not in df.columns:
             return json.dumps({"Error": f"Missing required column in data: {activity_col}"}, indent=4)

        # 1. Calculate the raw counts for each activity
        activity_counts = df[activity_col].value_counts()
        total_events = activity_counts.sum()

        if total_events == 0:
            return json.dumps({"Distribution": []}, indent=4)

        # 2. Create the distribution list
        distribution = []
        for activity, count in activity_counts.items():
            percentage = (count / total_events) * 100
            distribution.append({
                "activity": activity,
                "count": int(count),
                "percentage": round(percentage, 2)
            })

        # The result is already sorted by value_counts() (descending count)
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
    """
    Calculates the Happy-Path Compliance Rate. This is the percentage of cases 
    that exactly follow the specified happy path sequence of activities.

    The happy_path_data parameter expects an iterable (list/QuerySet) of 
    objects/dictionaries, and specifically handles the serialized dictionary format 
    provided by the user.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)

    # 1. Determine the list of happy path steps from the input structure
    happy_path_list = None
    
    if isinstance(happy_path_data, dict) and 'happy_paths' in happy_path_data:
        # Handles the internal test data format (dict wrapper)
        happy_path_list = happy_path_data['happy_paths']
    elif hasattr(happy_path_data, '__iter__') and not isinstance(happy_path_data, str):
        # Handles a direct list/QuerySet (e.g., the format provided by the user)
        happy_path_list = list(happy_path_data)
    
    if not happy_path_list:
        return json.dumps({"Error": "Happy path definition is missing or empty."}, indent=4)

    # 2. Sort the steps by 'serial_number' and extract the activity sequence
    try:
        # Sort the list using dictionary key access for 'serial_number'
        happy_path_list.sort(key=lambda item: item.get('serial_number', -1))
        
        target_path = []
        for item in happy_path_list:
            # Use .get() for safe dictionary key access, expecting 'activity_name'
            activity = item.get('activity_name')
            if activity is None:
                return json.dumps({"Error": "Happy path step is missing the 'activity_name' field."}, indent=4)
            target_path.append(activity)

        target_path_tuple = tuple(target_path)
        
    except Exception as e:
        # This catches errors if the list items aren't dictionaries or lack required keys
        return json.dumps({"Error": f"Failed to sort and extract happy path steps. Check data format: {e}"}, indent=4)

    if not target_path_tuple:
        return json.dumps({"Error": "Target happy path is empty after extraction."}, indent=4)

    try:
        df = pd.DataFrame(event_log_data)
        
        required_cols = [case_id_col, activity_col, start_time_col]
        if not all(col in df.columns for col in required_cols):
             missing = [col for col in required_cols if col not in df.columns]
             return json.dumps({"Error": f"Missing required columns in data: {missing}"}, indent=4)

        # 3. Prepare Data and sort events within cases by start time
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        # Sort by case ID and then by start time to guarantee the correct activity sequence
        df_sorted = df.sort_values(by=[case_id_col, start_time_col])

        # 4. Aggregate activity sequence (variant) for each case
        def get_case_sequence(group):
            return tuple(group[activity_col].tolist())

        # FIX: Added include_groups=False to resolve the FutureWarning
        case_sequences = df_sorted.groupby(case_id_col).apply(get_case_sequence, include_groups=False)
        
        total_cases = len(case_sequences)
        if total_cases == 0:
             return json.dumps({"Total_Cases_Analyzed": 0, "Compliance_Rate_Percentage": 0.0}, indent=4)

        # 5. Compare Paths and Count Compliance
        compliant_cases_count = 0
        for sequence in case_sequences:
            if sequence == target_path_tuple:
                compliant_cases_count += 1
        
        # 6. Calculate Metrics
        non_compliant_cases_count = total_cases - compliant_cases_count
        compliance_rate = (compliant_cases_count / total_cases) * 100
        non_compliance_rate = 100.0 - compliance_rate

        # 7. Format Output
        result = {
            "Total_Cases_Analyzed": int(total_cases),
            "Happy_Path_Definition": target_path,
            
            "Compliant_Cases_Count": int(compliant_cases_count),
            "Compliance_Rate_Percentage": round(compliance_rate, 2),
            
            "Non_Compliant_Cases_Count": int(non_compliant_cases_count),
            "Non_Compliance_Rate_Percentage": round(non_compliance_rate, 2),
            
            # Structure for Pie Chart visualization:
            "Pie_Chart_Data": [
                {"label": "Compliant", "value": round(compliance_rate, 2), "count": int(compliant_cases_count)},
                {"label": "Non-Compliant", "value": round(non_compliance_rate, 2), "count": int(non_compliant_cases_count)}
            ]
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during happy path compliance calculation: {e}"}, indent=4)




def calculate_total_completed_cases(event_log_data, case_id_col):
    """
    Calculates the total number of unique completed process instances (cases)
    in the event log. This is suitable for a KPI card metric.
    """
    if not event_log_data:
        return json.dumps({"Error": "Event log data is empty."}, indent=4)
    
    try:
        df = pd.DataFrame(event_log_data)
        
        if case_id_col not in df.columns:
             return json.dumps({"Error": f"Missing required column in data: {case_id_col}"}, indent=4)

        # Count the number of unique case IDs
        total_cases = df[case_id_col].nunique()

        # Format Output for a KPI card
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

    # 1. Determine the list of happy path steps and required length
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

        # 2. Prepare Data (Timestamps and Sorting)
        df[start_time_col] = pd.to_datetime(df[start_time_col], utc=True)
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)
        df_sorted = df.sort_values(by=[case_id_col, start_time_col])

        # 3. Calculate Cycle Times for All Cases
        case_start = df_sorted.groupby(case_id_col)[start_time_col].min().rename('Case_Start')
        case_end = df_sorted.groupby(case_id_col)[complete_time_col].max().rename('Case_End')
        df_cycle_times = pd.merge(case_start, case_end, on=case_id_col).reset_index()
        df_cycle_times['Cycle_Time_Seconds'] = (
            df_cycle_times['Case_End'] - df_cycle_times['Case_Start']
        ).dt.total_seconds()

        # 4. Aggregate Case Sequence and Steps Count
        case_metrics = df_sorted.groupby(case_id_col).agg(
            sequence=(activity_col, lambda x: tuple(x.tolist())),
            steps_count=(case_id_col, 'size') # Calculate step count
        ).reset_index()

        # 5. Merge all metrics
        df_metrics = pd.merge(case_metrics, df_cycle_times[[case_id_col, 'Cycle_Time_Seconds']], on=case_id_col)
        
        # 6. Identify Compliance
        df_metrics['Is_Compliant'] = df_metrics['sequence'] == target_path_tuple
        
        # 7. Determine Benchmark Time (T_min_HP)
        compliant_times = df_metrics[df_metrics['Is_Compliant']]['Cycle_Time_Seconds']
        if not compliant_times.empty:
            # Benchmark: Fastest time of a compliant case
            t_min_hp = compliant_times.min() 
        else:
            # Fallback: use overall minimum cycle time if no compliant cases exist
            t_min_hp = df_metrics['Cycle_Time_Seconds'].min() if not df_metrics.empty else 0

        # 8. Filter for Non-Compliant Cases and Calculate Deviation
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

        # Step Deviation: (Case Steps - Happy Path Steps)
        df_non_compliant['Step_Deviation'] = df_non_compliant['steps_count'] - happy_path_length
        
        # Time Deviation: (Case Cycle Time - Benchmark Time)
        df_non_compliant['Time_Deviation_Seconds'] = df_non_compliant['Cycle_Time_Seconds'] - t_min_hp

        # Calculate Averages (Only for Non-Compliant Cases)
        avg_step_deviation = df_non_compliant['Step_Deviation'].mean()
        avg_time_deviation_seconds = df_non_compliant['Time_Deviation_Seconds'].mean()

        # 9. Calculate Activity Deviation Distribution (for Bar Chart)
        happy_path_activities = set(target_path_tuple)
        
        # Get all activity events from ONLY non-compliant cases
        df_non_compliant_events = df[df[case_id_col].isin(df_non_compliant[case_id_col])]
        
        # Filter for activities in non-compliant cases that are NOT part of the Happy Path
        # This identifies the *extra* activities causing deviation
        non_hp_activities = df_non_compliant_events[~df_non_compliant_events[activity_col].isin(happy_path_activities)]
        
        # Calculate frequency of these deviating activities (Top 10)
        activity_deviation_counts = non_hp_activities[activity_col].value_counts().nlargest(10)

        activity_deviation_chart = [
            {"activity": act, "deviation_count": int(count)}
            for act, count in activity_deviation_counts.items()
        ]
        
        # 10. Format Final Output
        result = {
            "Total_Cases_Analyzed": len(df_metrics),
            "Non_Compliant_Cases_Count": total_non_compliant_cases,
            "Happy_Path_Length": happy_path_length,
            
            "Average_Step_Deviation": round(avg_step_deviation, 2),
            "Benchmark_Cycle_Time_Seconds": round(t_min_hp, 2),
            
            "Average_Time_Deviation_Seconds": round(avg_time_deviation_seconds, 2),
            "Average_Time_Deviation_Formatted": seconds_to_dhms(avg_time_deviation_seconds),

            # Data structure for the bar chart visualization
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

    # 1. Extract the set of mandatory Happy Path activities
    happy_path_list = None
    if isinstance(happy_path_data, dict) and 'happy_paths' in happy_path_data:
        happy_path_list = happy_path_data['happy_paths']
    elif hasattr(happy_path_data, '__iter__') and not isinstance(happy_path_data, str):
        happy_path_list = list(happy_path_data)
    
    if not happy_path_list:
        return json.dumps({"Error": "Happy path definition is missing or empty."}, indent=4)

    try:
        # Get the unique set of mandatory activities required in the process
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

        # 2. Group by case and get the set of unique activities performed in each case
        case_activities = df.groupby(case_id_col)[activity_col].apply(set)
        
        total_cases = len(case_activities)
        if total_cases == 0:
             return json.dumps({"Total_Cases_Analyzed": 0, "Skipped_Steps_Rate_Percentage": 0.0}, indent=4)

        skipped_cases_count = 0
        skipped_activity_counts = {}
        
        # 3. Check each case for skipped steps
        for case_id, actual_activities in case_activities.items():
            # Missing activities are the ones in mandatory set but not in actual set
            missing_activities = mandatory_activities - actual_activities
            
            if missing_activities:
                skipped_cases_count += 1
                # Tally the specific activities that were skipped
                for activity in missing_activities:
                    skipped_activity_counts[activity] = skipped_activity_counts.get(activity, 0) + 1
        
        # 4. Calculate Rate
        skipped_steps_rate = (skipped_cases_count / total_cases) * 100
        
        # 5. Prepare Bar Chart Data (Top 10 skipped activities)
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
            
            # Data structure for the bar chart visualization
            "Skipped_Activity_Distribution": skipped_activity_chart
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during skipped steps rate calculation: {e}"}, indent=4)






def calculate_case_throughput_rate(
    event_log_data, 
    case_id_col, 
    complete_time_col, # This variable receives 'columns.timestamp_end'
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

        # 1. Use the passed parameter 'complete_time_col' to read the original timestamp data
        df[complete_time_col] = pd.to_datetime(df[complete_time_col], utc=True)

        # 2. Identify Case Completion Time (latest event time per case)
        df_case_completion = (
            df.groupby(case_id_col)[complete_time_col]
            .max()
            .reset_index(name='Case_End') 
        )
        
        total_cases = len(df_case_completion)
        if total_cases == 0:
            return json.dumps({"Total_Cases_Completed": 0, "Throughput_Rate_Per_Period": 0.0}, indent=4)

        # 3. Handle Period Mapping and Date Formatting
        pd_resample_period = period
        date_format = "%Y-%m-%d"
        period_unit_text = "day"

        if period == 'W':
            # Use 'W' for resampling, setting the period unit for output
            period_unit_text = "week"
            date_format = "%Y-W%W"
        elif period == 'M':
            # Use 'ME' (Month End) to avoid FutureWarnings and the non-fixed frequency error
            pd_resample_period = 'ME'
            period_unit_text = "month"
            date_format = "%Y-%m" # Format as YYYY-MM
            
        # Calculate Total Process Duration based on period units
        min_completion_date = df_case_completion['Case_End'].min().date()
        max_completion_date = df_case_completion['Case_End'].max().date()
        total_days_span = (max_completion_date - min_completion_date).days + 1

        if period == 'W':
            total_time_units = max(1, math.ceil(total_days_span / 7))
        elif period == 'M':
            start_month = min_completion_date.year * 12 + min_completion_date.month
            end_month = max_completion_date.year * 12 + max_completion_date.month
            total_time_units = max(1, end_month - start_month + 1)
        else: # 'D'
            total_time_units = total_days_span
            
        # 4. Calculate Overall KPI Rate
        throughput_rate = total_cases / total_time_units if total_time_units > 0 else 0.0

        # 5. Prepare Line Chart Data (Cases Completed over time)
        
        # Set Case_End as index for temporal resampling. 
        df_case_completion = df_case_completion.set_index('Case_End')

        # Resample and count cases per period, using the mapped period (e.g., 'ME')
        cases_per_period = df_case_completion.resample(pd_resample_period)[case_id_col].count().rename('Cases_Completed')
        
        line_chart_data = []
        for timestamp, count in cases_per_period.items():
            if period == 'W':
                 # W-MON is used to get the start of the week for plotting consistency
                 formatted_period = timestamp.to_period('W-MON').start_time.strftime(date_format)
            else:
                 # For 'D' or 'ME', the timestamp is already a clean point in time (start of day or end of month)
                 # We simply format the index timestamp.
                 formatted_period = timestamp.strftime(date_format)
                 
            line_chart_data.append({
                "period": formatted_period,
                "count": int(count)
            })

        # 6. Format Output
        
        result = {
            "Total_Cases_Completed": int(total_cases),
            
            "Throughput_Rate_Per_Period": round(throughput_rate, 2),
            "Rate_Period_Unit": period_unit_text,
            
            # Data structure for Line Chart visualization
            "Throughput_Distribution": line_chart_data
        }
        
        return json.dumps(result, indent=4)

    except Exception as e:
        return json.dumps({"Error": f"An error occurred during throughput rate calculation: {e}"}, indent=4)