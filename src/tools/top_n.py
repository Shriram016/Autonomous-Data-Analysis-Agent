from typing import Any, Dict

import pandas as pd

from src.utils.helpers import _error_response, _success_response


def top_n(
    df: pd.DataFrame,
    N: int,
) -> Dict[str, Any]:
    """
    Return the first N rows of the DataFrame.

    This tool does NOT sort. It is the Planner's responsibility to call
    sort before top_n so that the df is ordered correctly before slicing.
    The Critic validates that sort precedes top_n in the plan.

    Parameters
    ----------
    df : Input DataFrame (should be pre-sorted by the caller).
    N  : Number of rows to return. Must be a positive integer.
         If N exceeds the number of rows in df, the entire df is
         returned with a message indicating the shortfall.

    Returns
    -------
    Standard response dict: {status, message, result}
    """

    # --- 1. Validate df ---
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a pandas DataFrame.")
    if df.empty:
        return _error_response("Input DataFrame is empty.")

    # --- 2. Validate N is a positive integer ---
    try:
        N = int(N)
    except (ValueError, TypeError):
        return _error_response(
            f"N must be a positive integer. Got: '{N}'."
        )

    if N <= 0:
        return _error_response(
            f"N must be a positive integer. Got: {N}."
        )

    # --- 3. Slice (return entire df if N exceeds available rows) ---
    row_count = len(df)

    if N > row_count:
        result = df.reset_index(drop=True)
        return _success_response(
            f"N ({N}) exceeds available rows ({row_count}). "
            f"Returning all {row_count} rows.",
            result
        )

    result = df.head(N).reset_index(drop=True)
    return _success_response(
        f"Returned top {N} rows from a {row_count}-row DataFrame.",
        result
    )
