# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# import pandas as pd
# import numpy as np
# import json
# from typing import Optional, List

# from .models import Project, DefineColumns, ProcessVariant
# from .utils import calculate_all_cycle_time_metrics  # Adjust if needed


# # ============================================================
# # ✅ Robust datetime conversion helper
# # ============================================================

# def robust_to_datetime(series, utc=True):
#     """Converts any timestamp series to UTC-aware pandas datetime."""
#     if series.empty:
#         return series

#     dt_series = pd.to_datetime(series, errors='coerce', infer_datetime_format=True)

#     if utc:
#         try:
#             # remove existing tz if any
#             dt_series = dt_series.dt.tz_localize(None, errors='coerce')
#         except Exception:
#             pass
#         # force UTC
#         dt_series = dt_series.dt.tz_localize('UTC', errors='coerce')

#     return dt_series


# # ============================================================
# # ✅ Event Log Filter Function (fully patched)
# # ============================================================

# def filter_event_log_pre_kpi(
#     df: pd.DataFrame,
#     case_id_col: str,
#     variant_col: str,
#     timestamp_start_col: str,
#     timestamp_complete_col: str,
#     start_date: Optional[pd.Timestamp] = None,
#     end_date: Optional[pd.Timestamp] = None,
#     selected_variants: Optional[List[str]] = None,
#     min_cycle_time: Optional[float] = None,
#     max_cycle_time: Optional[float] = None,
#     time_unit: str = "hours"
# ) -> pd.DataFrame:
#     """Filter the event log by date, variant, and cycle time."""

#     filtered_df = df.copy()

#     # --- 1️⃣ Convert timestamp columns ---
#     filtered_df[timestamp_start_col] = robust_to_datetime(filtered_df[timestamp_start_col])
#     filtered_df[timestamp_complete_col] = robust_to_datetime(filtered_df[timestamp_complete_col])
#     filtered_df = filtered_df.dropna(subset=[timestamp_start_col, timestamp_complete_col])

#     if filtered_df.empty:
#         return filtered_df

#     # --- 2️⃣ Convert start/end dates safely ---
#     if start_date is not None and not isinstance(start_date, pd.Timestamp):
#         start_date = pd.to_datetime(start_date, errors='coerce', utc=True)
#     if end_date is not None and not isinstance(end_date, pd.Timestamp):
#         end_date = pd.to_datetime(end_date, errors='coerce', utc=True)

#     if pd.isna(start_date):
#         start_date = None
#     if pd.isna(end_date):
#         end_date = None

#     # --- 3️⃣ Date filtering (critical fix: reconvert grouped column) ---
#     case_start_times = filtered_df.groupby(case_id_col)[timestamp_start_col].min().reset_index()
#     case_start_times[timestamp_start_col] = pd.to_datetime(
#         case_start_times[timestamp_start_col], errors='coerce', utc=True
#     )

#     if start_date is not None:
#         valid_cases = case_start_times.loc[
#             case_start_times[timestamp_start_col] >= start_date, case_id_col
#         ]
#         filtered_df = filtered_df[filtered_df[case_id_col].isin(valid_cases)]

#     if end_date is not None:
#         case_start_times = filtered_df.groupby(case_id_col)[timestamp_start_col].min().reset_index()
#         case_start_times[timestamp_start_col] = pd.to_datetime(
#             case_start_times[timestamp_start_col], errors='coerce', utc=True
#         )
#         valid_cases = case_start_times.loc[
#             case_start_times[timestamp_start_col] <= end_date, case_id_col
#         ]
#         filtered_df = filtered_df[filtered_df[case_id_col].isin(valid_cases)]

#     # --- 4️⃣ Variant filter ---
#     if selected_variants and len(selected_variants) > 0:
#         case_activities = filtered_df.groupby(case_id_col)[variant_col].apply(list).reset_index(name='activities')
#         case_activities['calculated_variant_path'] = case_activities['activities'].apply(
#             lambda x: ' -> '.join(x)
#         )

#         clean_calculated_paths = case_activities['calculated_variant_path'].str.lower().str.strip()
#         clean_selected_variants = [v.lower().strip() for v in selected_variants]

#         matching_case_ids = case_activities[
#             clean_calculated_paths.isin(clean_selected_variants)
#         ][case_id_col].unique()

#         filtered_df = filtered_df[filtered_df[case_id_col].isin(matching_case_ids)]

#     # --- 5️⃣ Cycle time filter ---
#     if min_cycle_time is not None or max_cycle_time is not None:
#         case_times = filtered_df.groupby(case_id_col).agg(
#             case_start=(timestamp_start_col, 'min'),
#             case_end=(timestamp_complete_col, 'max')
#         ).reset_index()

#         case_times['cycle_time_delta'] = case_times['case_end'] - case_times['case_start']
#         unit_factor = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
#         divisor = unit_factor.get(time_unit.lower(), 3600)
#         case_times['cycle_time_unit'] = case_times['cycle_time_delta'].dt.total_seconds() / divisor

#         valid_cases = case_times.copy()
#         if min_cycle_time is not None:
#             valid_cases = valid_cases[valid_cases['cycle_time_unit'] >= min_cycle_time]
#         if max_cycle_time is not None:
#             valid_cases = valid_cases[valid_cases['cycle_time_unit'] <= max_cycle_time]

#         filtered_df = filtered_df[filtered_df[case_id_col].isin(valid_cases[case_id_col])]

#     return filtered_df
