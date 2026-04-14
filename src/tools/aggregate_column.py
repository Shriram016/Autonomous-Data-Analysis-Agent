from typing import Any, Dict

import pandas as pd

from src.utils.helpers import _error_response, _success_response


_ALLOWED_OPERATIONS = {"sum", "mean", "min", "max", "count"}


def aggregate_column(
    df: pd.DataFrame,
    col_name: str,
    operation: str,
    new_col_name: str,
) -> Dict[str, Any]:
    """
    Compute a single aggregate value over an entire column — no grouping.

    Parameters
    ----------
    df           : Input DataFrame.
    col_name     : Column to aggregate. Must be numeric.
    operation    : One of: "sum", "mean", "min", "max"
    new_col_name : Name for the result column. Convention: {col}_{op}, e.g. "Sales_sum"

    Returns
    -------
    Standard response dict: {status, message, result}
    Result is a 1-row DataFrame with a single column named new_col_name.
    """

    # --- 1. Validate df ---
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a pandas DataFrame.")
    if df.empty:
        return _error_response("Input DataFrame is empty.")

    # --- 2. Validate col_name ---
    if col_name not in df.columns:
        return _error_response(
            f"Column '{col_name}' not found in DataFrame. "
            f"Available columns: {list(df.columns)}"
        )

    # --- 3. Validate operation ---
    if operation not in _ALLOWED_OPERATIONS:
        return _error_response(
            f"Invalid operation '{operation}'. "
            f"Allowed values: {sorted(_ALLOWED_OPERATIONS)}."
        )

    # --- 4. Validate column is numeric (skip for count — works on any dtype) ---
    if operation != "count" and not pd.api.types.is_numeric_dtype(df[col_name]):
        return _error_response(
            f"Column '{col_name}' is not numeric (dtype: {df[col_name].dtype}). "
            f"Operations sum/mean/min/max require a numeric column. Use 'count' for non-numeric."
        )

    # --- 5. Compute ---
    try:
        value = df[col_name].agg(operation)
        result = pd.DataFrame({new_col_name: [value]})
    except Exception as e:
        return _error_response(f"aggregate_column failed: {str(e)}")

    return _success_response(
        f"Computed {operation} of '{col_name}' across {len(df)} rows: {value:.4f}.",
        result,
    )
