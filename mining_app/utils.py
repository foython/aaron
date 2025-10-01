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