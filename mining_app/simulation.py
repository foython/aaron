from copy import deepcopy
import pandas as pd
import json
import re
from .models import DefineColumns
from .utils import analyze_and_structure_process_datas


def simulate_process_analysis(
    project,
    remove_bottlenecks=False,
    remove_loops=False,
    remove_dropouts=False,
    target_activity=None
):
    """
    Virtually simulates process improvements (remove bottlenecks, loops, dropouts)
    using real process data.
    
    If `target_activity` is provided, only that activity is adjusted.
    Otherwise, all matching issues are simulated as before.
    """

    # ---- 1. Load CSV and columns ----
    columns = DefineColumns.objects.get(project=project)
    file_path = project.csv_file.path
    df = pd.read_csv(file_path)

    case_id = columns.case_id
    activity = columns.activity
    start = columns.timestamp_start
    end = columns.timestamp_end

    # ---- 2. Generate original structured analysis ----
    result_json = analyze_and_structure_process_datas(
        df.to_dict("records"),
        case_id,
        activity,
        start,
        end
    )
    result_data = json.loads(result_json)

    global_metrics = deepcopy(result_data.get("global_metrics", {}))
    process_nodes = deepcopy(result_data.get("process_flow_nodes", []))

    # ---- 3. Extract issue sets ----
    bottlenecks = [n for n in process_nodes if n.get("isBottleneck")]
    loops = [n for n in process_nodes if n.get("hasLoop")]
    dropouts = [n for n in process_nodes if n.get("isDropout")]

    # ---- 4. Apply virtual simulation ----
    for node in process_nodes:
        duration_val = float(node.get("value", 0))
        label = node.get("label")

        # 🎯 If target_activity specified → only modify that one
        if target_activity and label.lower() != target_activity.lower():
            continue

        # Bottleneck adjustment
        if remove_bottlenecks and node.get("isBottleneck"):
            node["isBottleneck"] = False
            node["descriptions"].append("Simulated: Bottleneck resolved (duration normalized).")
            node["value"] = str(round(duration_val * 0.7, 2))  # reduce duration by 30%

        # Loop removal
        if remove_loops and node.get("hasLoop"):
            node["hasLoop"] = False
            node["loopConnections"] = None
            node["descriptions"].append("Simulated: Loop eliminated (no rework).")

        # Dropout prevention
        if remove_dropouts and node.get("isDropout"):
            node["isDropout"] = False
            node["descriptions"].append("Simulated: Dropout prevented (case completed).")

    # ---- 5. Parse and adjust global cycle times ----
    def parse_cycle_to_hours(time_str):
        d = h = m = 0
        match = re.findall(r"(\d+)\s*d", time_str)
        if match: d = int(match[0])
        match = re.findall(r"(\d+)\s*h", time_str)
        if match: h = int(match[0])
        match = re.findall(r"(\d+)\s*m", time_str)
        if match: m = int(match[0])
        return round(d * 24 + h + m / 60, 2)

    cycle_time = global_metrics.get("Cycle_Time", {})
    avg_ct_hours = parse_cycle_to_hours(cycle_time.get("Average", "0h"))
    median_ct_hours = parse_cycle_to_hours(cycle_time.get("Median", "0h"))

    # Adjustment factor (smarter: scale by what was fixed)
    adjustment_factor = 1.0
    if remove_bottlenecks:
        adjustment_factor *= 0.8
    if remove_loops:
        adjustment_factor *= 0.9
    if remove_dropouts:
        adjustment_factor *= 0.95

    # If only one activity targeted, apply smaller effect
    if target_activity:
        adjustment_factor = 1 - (1 - adjustment_factor) * 0.4

    adjusted_avg = round(avg_ct_hours * adjustment_factor, 2)
    adjusted_median = round(median_ct_hours * adjustment_factor, 2)

    # ---- 6. Update metrics ----
    global_metrics["Cycle_Time"]["Average"] = f"{adjusted_avg}h (simulated)"
    global_metrics["Cycle_Time"]["Median"] = f"{adjusted_median}h (simulated)"

    global_metrics["Simulation_Parameters"] = {
        "remove_bottlenecks": remove_bottlenecks,
        "remove_loops": remove_loops,
        "remove_dropouts": remove_dropouts,
        "target_activity": target_activity or "ALL"
    }

    global_metrics["Simulation_Summary"] = {
        "Original_Cycle_Time_Hours": avg_ct_hours,
        "Adjusted_Cycle_Time_Hours": adjusted_avg,
        "Estimated_Improvement_%": round((1 - adjusted_avg / avg_ct_hours) * 100, 2)
        if avg_ct_hours > 0 else 0.0
    }

    # ---- 7. Return simulated output ----
    simulated_result = {
        "global_metrics": global_metrics,
        "process_flow_nodes": process_nodes
    }

    return simulated_result
