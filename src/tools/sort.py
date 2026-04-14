from typing import Any, Dict

import pandas as pd

from src.utils.helpers import _error_response, _success_response


SUPPORTED_ORDERS = {"asc", "desc"}


def sort(
    df: pd.DataFrame,
    sort_col: Dict[str, str],
) -> Dict[str, Any]:
    """
    Sort the DataFrame by one or more columns.

    Parameters
    ----------
    df       : Input DataFrame.
    sort_col : Dict mapping each column name to its sort order.
               Key   = column name to sort by (numeric, string, or datetime).
               Value = "asc" (ascending) or "desc" (descending).
               Single column  : {"Sales_sum": "desc"}
               Multi-column   : {"Sales_sum": "desc", "Customer Name": "asc"}
               Columns are applied left to right as sort priority.

               Sorting behaviour by dtype:
                 numeric  -> lowest to highest (asc) / highest to lowest (desc)
                 string   -> alphabetical (asc) / reverse alphabetical (desc)
                 datetime -> oldest to newest (asc) / newest to oldest (desc)

    Returns
    -------
    Standard response dict: {status, message, result}
    """

    # --- 1. Validate df ---
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a pandas DataFrame.")
    if df.empty:
        return _error_response("Input DataFrame is empty.")

    # --- 2. Validate sort_col is a non-empty dict ---
    if not isinstance(sort_col, dict) or not sort_col:
        return _error_response(
            "sort_col must be a non-empty dict mapping column names to order. "
            "Example: {\"Sales_sum\": \"desc\"}"
        )

    # --- 3. Validate each column: exists and valid order ---
    for col, order in sort_col.items():

        if col not in df.columns:
            return _error_response(
                f"Column '{col}' not found in DataFrame. "
                f"Available columns: {list(df.columns)}"
            )

        if order not in SUPPORTED_ORDERS:
            return _error_response(
                f"Invalid order '{order}' for column '{col}'. "
                f"Supported values: {sorted(SUPPORTED_ORDERS)}."
            )

    # --- 4. Build sort parameters ---
    cols      = list(sort_col.keys())
    ascending = [sort_col[col] == "asc" for col in cols]

    # --- 5. Sort ---
    try:
        sorted_df = df.sort_values(by=cols, ascending=ascending).reset_index(drop=True)
    except Exception as e:
        return _error_response(
            f"sort failed on column(s) {cols}: {str(e)}. "
            f"This can happen when a column contains mixed types or incomparable values."
        )

    sort_summary = ", ".join(f"'{c}' {o}" for c, o in sort_col.items())
    return _success_response(
        f"Sorted {len(sorted_df)} rows by {sort_summary}.",
        sorted_df
    )
