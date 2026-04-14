from typing import Any, Dict, List, Union

import pandas as pd

from src.utils.helpers import _error_response, _success_response


NUMERIC_OPS  = {"sum", "mean", "count", "min", "max", "median", "std"}
OBJECT_OPS   = {"count"}
DATETIME_OPS = {"min", "max", "count"}
ALL_OPS      = NUMERIC_OPS | OBJECT_OPS | DATETIME_OPS


def groupby_aggregate(
    df: pd.DataFrame,
    group_col: Union[str, List[str]],
    agg_col: Dict[str, str],
    ) -> Dict[str, Any]:
    """
    Group the DataFrame and aggregate one or more columns.

    Parameters
    ----------
    df        : Input DataFrame.
    group_col : Column(s) to group by. Accepts a single column name or a list.
                Examples: "Category"  or  ["Category", "Order Month"]
    agg_col   : Dict mapping each aggregation column to its operation.
                Key   = column name to aggregate.
                Value = operation: "sum", "mean", "count", "min", "max", "median", "std"
                Allowed operations depend on the column dtype:
                  numeric  -> sum, mean, count, min, max, median, std
                  object   -> count
                  datetime -> min, max, count
                Example: {"Sales": "sum", "Profit": "mean"}

    Output column naming (fixed pattern for Planner predictability):
        {col}_{operation}  ->  Sales_sum, Profit_mean, Order Date_min

    Returns
    -------
    Standard response dict: {status, message, result}
    """

    # --- 1. Validate df ---
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a pandas DataFrame.")
    if df.empty:
        return _error_response("Input DataFrame is empty.")

    # --- 2. Normalise group_col to a list ---
    if isinstance(group_col, str):
        group_cols = [group_col]
    elif isinstance(group_col, list):
        group_cols = group_col
    else:
        return _error_response(
            "group_col must be a column name (string) or a list of column names."
        )

    if not group_cols:
        return _error_response("group_col must not be empty.")

    # --- 3. Validate group_col columns exist ---
    missing_group = [c for c in group_cols if c not in df.columns]
    if missing_group:
        return _error_response(
            f"Group column(s) not found in DataFrame: {missing_group}. "
            f"Available columns: {list(df.columns)}"
        )

    # --- 4. Validate agg_col is a non-empty dict ---
    if not isinstance(agg_col, dict) or not agg_col:
        return _error_response(
            "agg_col must be a non-empty dict mapping column names to operations. "
            "Example: {\"Sales\": \"sum\", \"Profit\": \"mean\"}"
        )

    # --- 5. Validate each agg column: exists + operation compatible with dtype ---
    for col, op in agg_col.items():

        if col not in df.columns:
            return _error_response(
                f"Aggregation column '{col}' not found in DataFrame. "
                f"Available columns: {list(df.columns)}"
            )

        if op not in ALL_OPS:
            return _error_response(
                f"Invalid operation '{op}' for column '{col}'. "
                f"Supported operations: {sorted(ALL_OPS)}."
            )

        col_dtype = df[col].dtype

        if pd.api.types.is_numeric_dtype(col_dtype):
            allowed = NUMERIC_OPS
        elif pd.api.types.is_datetime64_any_dtype(col_dtype):
            allowed = DATETIME_OPS
        else:
            allowed = OBJECT_OPS

        if op not in allowed:
            return _error_response(
                f"Operation '{op}' is not allowed for column '{col}' "
                f"(dtype: {col_dtype}). "
                f"Allowed operations for this dtype: {sorted(allowed)}."
            )

    # --- 6. Run groupby + aggregate ---
    # KNOWN EDGE CASE: if group_col and agg_col share the same column name
    # (e.g., group by "Category", count "Category"), pandas overwrites the group
    # column with the aggregated values after reset_index, causing group labels to
    # disappear from the output. Counts are correct but category names are lost.
    # Workaround: Planner should always count a different column (e.g., "Order ID")
    # rather than the group column itself.
    try:
        grouped = df.groupby(group_cols, as_index=False).agg(agg_col)
    except Exception as e:
        return _error_response(f"groupby_aggregate failed: {str(e)}")

    # --- 7. Rename aggregated columns to fixed pattern: col_operation ---
    rename_map = {col: f"{col}_{op}" for col, op in agg_col.items()}
    grouped = grouped.rename(columns=rename_map)

    agg_summary = ", ".join(f"'{col}' {op}" for col, op in agg_col.items())
    group_summary = group_cols if len(group_cols) > 1 else group_cols[0]

    return _success_response(
        f"Grouped by {group_summary}, aggregated: {agg_summary}. "
        f"Result has {len(grouped)} rows.",
        grouped
    )
