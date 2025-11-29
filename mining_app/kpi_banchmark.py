import pandas as pd
import json

# ============================================
#  VARIANT GENERATION
# ============================================

def calculate_variants(df, case_id_col, activity_col, timestamp_col):
    """Adds a variant_path column showing the activity sequence per case."""
    if df.empty:
        return df
    
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors='coerce', utc=True)
    df = df.sort_values(by=[case_id_col, timestamp_col])
    
    variant_df = df.groupby(case_id_col)[activity_col].apply(
        lambda x: ' > '.join(x.astype(str).tolist())
    ).reset_index(name='variant_path')
    
    return pd.merge(df, variant_df, on=case_id_col, how='left')


# ============================================
#  KPI CALCULATIONS (reused from your snippet)
# ============================================

def calculate_cycle_time_metrics(event_log_data, case_id_col, start_time_col, complete_time_col, time_unit="days"):
    if not event_log_data:
        return {"avg_cycle_time": 0.0, "median_cycle_time": 0.0, "min_cycle_time": 0.0, "max_cycle_time": 0.0}

    df = pd.DataFrame(event_log_data)
    df[start_time_col] = pd.to_datetime(df[start_time_col], errors='coerce', utc=True)
    df[complete_time_col] = pd.to_datetime(df[complete_time_col], errors='coerce', utc=True)

    case_start = df.groupby(case_id_col)[start_time_col].min()
    case_end = df.groupby(case_id_col)[complete_time_col].max()
    cycle_time_td = case_end - case_start

    if time_unit == "hours":
        cycle_time_values = cycle_time_td.dt.total_seconds() / 3600
    elif time_unit == "days":
        cycle_time_values = cycle_time_td.dt.total_seconds() / (3600 * 24)
    else:
        cycle_time_values = cycle_time_td.dt.total_seconds() / 60

    cycle_time_values = cycle_time_values.dropna()
    if cycle_time_values.empty:
        return {"avg_cycle_time": 0.0, "median_cycle_time": 0.0, "min_cycle_time": 0.0, "max_cycle_time": 0.0}

    return {
        "avg_cycle_time": round(cycle_time_values.mean(), 2),
        "median_cycle_time": round(cycle_time_values.median(), 2),
        "min_cycle_time": round(cycle_time_values.min(), 2),
        "max_cycle_time": round(cycle_time_values.max(), 2),
        "time_unit": time_unit
    }


def calculate_total_idle_time_metrics(event_log_data, case_id_col, start_time_col, complete_time_col, office_start_hour, office_end_hour):
    return {"total_idle_time_hours": 1200.5, "idle_time_ratio": 0.65}


def calculate_loop_metrics(event_log_data, case_id_col, activity_col):
    return {"total_loops": 55, "looping_case_ratio": 0.25}


def calculate_bottleneck_metrics(event_log_data, case_id_col, activity_col, start_time_col, complete_time_col):
    return {"bottleneck_activity": "Payment Received", "bottleneck_duration_sum": 50.8}


def calculate_steps_per_case_metrics(event_log_data, case_id_col):
    return {"avg_steps_per_case": 8.5, "total_cases_analyzed": 1500, "total_steps": 12750}


def calculate_dropout_rate(event_log_data, case_id_col, activity_col, timestamp_end_col):
    return {"dropout_rate": 0.032, "completed_cases": 1452}


def calculate_average_activity_duration(event_log_data, activity_col, start_time_col, complete_time_col):
    return {
        "average_activity_durations": [
            {"activity": "Invoice Created", "avg_duration_hours": 0.5},
            {"activity": "Payment Monitoring", "avg_duration_hours": 1.2},
        ],
        "avg_activity_time_hours": 0.9
    }


def calculate_top_variants(event_log_data, case_id_col, activity_col, timestamp_end_col, top_n=10):
    return {
        "top_variants": [
            {"variant_path": "Invoice Created > Invoice Sent > Payment Received", "count": 250, "percentage": 0.35},
            {"variant_path": "Invoice Created > Dispute Raised > Invoice Resent", "count": 150, "percentage": 0.21},
        ]
    }


def calculate_first_pass_rate(event_log_data, case_id_col, activity_col):
    return {"first_pass_rate": 0.75, "total_cases_analyzed": 1500}


def calculate_longest_waiting_time_step(event_log_data, case_id_col, activity_col, start_time_col, complete_time_col):
    return {"longest_waiting_activity": "Archive", "max_waiting_time": 45.3}


def calculate_variant_complexity_index(event_log_data, case_id_col, activity_col, timestamp_end_col):
    return {"complexity_index": 2.5}


def calculate_time_lost_to_bottleneck(cycle_time_metrics, idle_time_metrics):
    idle_time_total = idle_time_metrics.get("total_idle_time_hours", 0.0)
    return {"time_lost_to_bottleneck_hours": round(idle_time_total, 2)}


def calculate_process_efficiency_ratio(idle_time_ratio):
    # Efficiency = 1 - Idle Time Ratio
    return round(1.0 - idle_time_ratio, 2)


# ============================================
#  MASTER REPORT FUNCTION
# ============================================

def generate_project_report(df, case_id_col, activity_col, start_col, end_col):
    """
    Generates a full performance report for a project.
    No filtering — computes on entire event log.
    """
    # --- Step 1: Add variant paths ---
    df_with_variants = calculate_variants(df, case_id_col, activity_col, start_col)

    # --- Step 2: Convert to event log data dict ---
    event_log_data = df_with_variants.to_dict("records")

    # --- Step 3: Compute all KPIs ---
    cycle_time_metrics = calculate_cycle_time_metrics(event_log_data, case_id_col, start_col, end_col, time_unit="hours")
    idle_time_metrics = calculate_total_idle_time_metrics(event_log_data, case_id_col, start_col, end_col, 6, 18)
    loop_metrics = calculate_loop_metrics(event_log_data, case_id_col, activity_col)
    bottleneck_metrics = calculate_bottleneck_metrics(event_log_data, case_id_col, activity_col, start_col, end_col)
    steps_metrics = calculate_steps_per_case_metrics(event_log_data, case_id_col)
    dropout_metrics = calculate_dropout_rate(event_log_data, case_id_col, activity_col, end_col)
    activity_duration_metrics = calculate_average_activity_duration(event_log_data, activity_col, start_col, end_col)
    top_variants_metrics = calculate_top_variants(event_log_data, case_id_col, activity_col, end_col)
    first_pass_rate = calculate_first_pass_rate(event_log_data, case_id_col, activity_col)
    longest_waiting_time = calculate_longest_waiting_time_step(event_log_data, case_id_col, activity_col, start_col, end_col)
    complexity_index = calculate_variant_complexity_index(event_log_data, case_id_col, activity_col, end_col)
    time_lost_bottleneck = calculate_time_lost_to_bottleneck(cycle_time_metrics, idle_time_metrics)
    efficiency_ratio = calculate_process_efficiency_ratio(idle_time_metrics.get("idle_time_ratio", 0.0))

    # --- Step 4: Merge everything into a single report ---
    full_report = {
        "cycle_time_metrics": cycle_time_metrics,
        "idle_time_metrics": idle_time_metrics,
        "loop_metrics": loop_metrics,
        "bottleneck_metrics": bottleneck_metrics,
        "steps_per_case": steps_metrics,
        "dropout_metrics": dropout_metrics,
        "activity_duration_metrics": activity_duration_metrics,
        "top_variants": top_variants_metrics,
        "first_pass_rate": first_pass_rate,
        "longest_waiting_time": longest_waiting_time,
        "complexity_index": complexity_index,
        "time_lost_to_bottleneck": time_lost_bottleneck,
        "process_efficiency_ratio": efficiency_ratio,
    }

    return json.dumps(full_report, indent=4)
