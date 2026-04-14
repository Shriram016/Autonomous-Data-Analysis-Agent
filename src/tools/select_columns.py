from typing import Any, Dict, List

import pandas as pd

from src.utils.helpers import _error_response, _success_response


def select_columns(
    df: pd.DataFrame,
    col_list: List[str],
) -> Dict[str, Any]:
    """
    Return a DataFrame with only the specified columns.

    Parameters
    ----------
    df       : Input DataFrame.
    col_list : List of column names to keep. Order is preserved.
               Duplicates are silently removed (first occurrence kept).
               All columns must exist in df — partial matches are not allowed.

    Returns
    -------
    Standard response dict: {status, message, result}
    """

    # --- 1. Validate df ---
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a pandas DataFrame.")
    if df.empty:
        return _error_response("Input DataFrame is empty.")

    # --- 2. Validate col_list is a non-empty list ---
    if not isinstance(col_list, list) or not col_list:
        return _error_response(
            "col_list must be a non-empty list of column names. "
            "Example: [\"Category\", \"Sales_sum\"]"
        )

    # --- 3. Deduplicate while preserving order ---
    seen = set()
    deduped = []
    for col in col_list:
        if col not in seen:
            deduped.append(col)
            seen.add(col)

    duplicates_removed = len(col_list) - len(deduped)

    # --- 4. Validate all columns exist ---
    missing = [c for c in deduped if c not in df.columns]
    if missing:
        return _error_response(
            f"Column(s) not found in DataFrame: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    # --- 5. Select ---
    result = df[deduped].reset_index(drop=True)

    message = f"Selected {len(deduped)} column(s): {deduped}."
    if duplicates_removed:
        message += f" ({duplicates_removed} duplicate(s) removed from col_list.)"

    return _success_response(message, result)
