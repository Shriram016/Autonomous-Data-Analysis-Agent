import re
from typing import Any, Dict, Optional, Union

import pandas as pd

from src.utils.helpers import _error_response, _success_response


def date_filter(
    df: pd.DataFrame,
    col_name: str,
    time_period: str,
    end_date: Optional[Union[str, pd.Timestamp]] = None,
) -> Dict[str, Any]:
    """
    Filter rows where col_name falls within [end_date - time_period, end_date].

    Parameters
    ----------
    df          : Input DataFrame.
    col_name    : Name of the datetime column to filter on.
    time_period : How far back from end_date to include.
                  Format: <number><unit> where unit is D (days), M (months), Y (years).
                  Examples: "10D", "3M", "1Y"
    end_date    : Upper bound of the date range (inclusive).
                  Accepts a date string ("2023-12-31") or a pd.Timestamp.
                  Defaults to the maximum value in col_name when not provided.

    Returns
    -------
    Standard response dict: {status, message, result}
    """

    # --- 1. Validate df ---
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a pandas DataFrame.")
    if df.empty:
        return _error_response("Input DataFrame is empty.")

    # --- 2. Validate col_name exists ---
    if col_name not in df.columns:
        return _error_response(
            f"Column '{col_name}' not found in DataFrame. "
            f"Available columns: {list(df.columns)}"
        )

    # --- 3. Parse col_name as datetime ---
    working_df = df.copy()
    try:
        working_df[col_name] = pd.to_datetime(working_df[col_name], errors="raise")
    except Exception as e:
        return _error_response(
            f"Could not parse column '{col_name}' as datetime: {str(e)}"
        )

    # --- 4. Resolve end_date ---
    if end_date is None:
        resolved_end = working_df[col_name].max()
    else:
        try:
            resolved_end = pd.to_datetime(end_date, errors="raise")
        except Exception as e:
            return _error_response(
                f"Could not parse end_date '{end_date}' as a date: {str(e)}"
            )

    # --- 5. Parse time_period ---
    pattern = re.fullmatch(r"(\d+)(D|M|Y)", time_period.strip().upper())
    if not pattern:
        return _error_response(
            f"Invalid time_period format '{time_period}'. "
            "Expected format: <number><unit> where unit is D (days), M (months), or Y (years). "
            "Examples: '10D', '3M', '1Y'"
        )

    amount = int(pattern.group(1))
    unit = pattern.group(2)

    if amount <= 0:
        return _error_response(
            f"time_period amount must be a positive integer. Got: {amount}"
        )

    offset_map = {
        "D": pd.DateOffset(days=amount),
        "M": pd.DateOffset(months=amount),
        "Y": pd.DateOffset(years=amount),
    }
    resolved_start = resolved_end - offset_map[unit]

    # --- 6. Apply filter ---
    mask = (working_df[col_name] >= resolved_start) & (working_df[col_name] <= resolved_end)
    filtered_df = working_df[mask].reset_index(drop=True)

    # --- 7. Validate result is not empty ---
    if filtered_df.empty:
        return _error_response(
            f"No rows found between {resolved_start.date()} and {resolved_end.date()} "
            f"in column '{col_name}'. Try a wider time_period or check end_date."
        )

    return _success_response(
        f"Filtered {len(filtered_df)} rows between {resolved_start.date()} "
        f"and {resolved_end.date()} in column '{col_name}'.",
        filtered_df
    )
