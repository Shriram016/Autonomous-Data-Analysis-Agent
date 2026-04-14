from typing import Any, Dict

import pandas as pd

from src.utils.helpers import _error_response, _success_response


SUPPORTED_PARTS = {"month", "year", "quarter", "day"}


def extract_date_part(
    df: pd.DataFrame,
    col_name: str,
    part: str,
    new_col_name: str,
) -> Dict[str, Any]:
    """
    Extract a date component from a datetime column into a new readable column.

    Parameters
    ----------
    df           : Input DataFrame.
    col_name     : Name of the datetime column to extract from.
    part         : Date component to extract.
                   "month"   → "January", "February", ... (string)
                   "year"    → 2017, 2018, ...            (integer)
                   "quarter" → "Q1", "Q2", "Q3", "Q4"    (string)
                   "day"     → 1, 2, 3, ... 31            (integer)
    new_col_name : Name of the new column to create. Must not already exist in df.

    Returns
    -------
    Standard response dict: {status, message, result}
    """

    # --- 1. Validate df ---
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a pandas DataFrame.")
    if df.empty:
        return _error_response("Input DataFrame is empty.")

    # --- 2. Validate part ---
    if part not in SUPPORTED_PARTS:
        return _error_response(
            f"Invalid part '{part}'. "
            f"Supported parts: {sorted(SUPPORTED_PARTS)}."
        )

    # --- 3. Validate col_name exists ---
    if col_name not in df.columns:
        return _error_response(
            f"Column '{col_name}' not found in DataFrame. "
            f"Available columns: {list(df.columns)}"
        )

    # --- 4. Validate new_col_name does not already exist ---
    if new_col_name in df.columns:
        return _error_response(
            f"Column '{new_col_name}' already exists in the DataFrame. "
            f"Choose a different new_col_name."
        )

    # --- 5. Parse col_name as datetime ---
    working_df = df.copy()
    try:
        working_df[col_name] = pd.to_datetime(working_df[col_name], errors="raise")
    except Exception as e:
        return _error_response(
            f"Could not parse column '{col_name}' as datetime: {str(e)}"
        )

    # --- 6. Extract date part ---
    dt = working_df[col_name].dt

    if part == "month":
        working_df[new_col_name] = dt.month_name()
    elif part == "year":
        working_df[new_col_name] = dt.year.astype(int)
    elif part == "quarter":
        working_df[new_col_name] = "Q" + dt.quarter.astype(str)
    elif part == "day":
        working_df[new_col_name] = dt.day.astype(int)

    return _success_response(
        f"Extracted '{part}' from '{col_name}' into new column '{new_col_name}'.",
        working_df
    )
