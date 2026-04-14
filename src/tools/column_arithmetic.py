from typing import Any, Dict

import pandas as pd

from src.utils.helpers import _error_response, _success_response


SUPPORTED_OPERATIONS = {"+", "-", "*", "/"}


def column_arithmetic(
    df: pd.DataFrame,
    col1: str,
    col2: str,
    operation: str,
    new_col_name: str,
    is_datetime: bool = False,
) -> Dict[str, Any]:
    """
    Perform arithmetic between two columns and store the result in a new column.

    Parameters
    ----------
    df           : Input DataFrame.
    col1         : Left-hand column name.
    col2         : Right-hand column name.
    operation    : Arithmetic operation to apply.
                   Numeric mode  → "+", "-", "*", "/"
                   Datetime mode → only "-" is valid (col1 - col2 = days as integer)
    new_col_name : Name of the new result column. Must not already exist in df.
    is_datetime  : If True, treat col1 and col2 as datetime columns and compute
                   the difference in whole days (col1 - col2).
                   If False, treat both columns as numeric.

    Returns
    -------
    Standard response dict: {status, message, result}
    """

    # --- 1. Validate df ---
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a pandas DataFrame.")
    if df.empty:
        return _error_response("Input DataFrame is empty.")

    # --- 2. Validate both columns exist ---
    missing = [c for c in [col1, col2] if c not in df.columns]
    if missing:
        return _error_response(
            f"Column(s) not found in DataFrame: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    # --- 3. Validate new_col_name does not already exist ---
    if new_col_name in df.columns:
        return _error_response(
            f"Column '{new_col_name}' already exists in the DataFrame. "
            f"Choose a different new_col_name."
        )

    # --- 4. Validate operation ---
    if operation not in SUPPORTED_OPERATIONS:
        return _error_response(
            f"Invalid operation '{operation}'. "
            f"Supported operations: {sorted(SUPPORTED_OPERATIONS)}."
        )

    working_df = df.copy()
    warning = None

    # --- 5. Datetime branch ---
    if is_datetime:
        if operation != "-":
            return _error_response(
                f"Only '-' is supported for datetime columns. Got: '{operation}'."
            )

        for col in [col1, col2]:
            try:
                working_df[col] = pd.to_datetime(working_df[col], errors="raise")
            except Exception as e:
                return _error_response(
                    f"Could not parse column '{col}' as datetime: {str(e)}"
                )

        diff = working_df[col1] - working_df[col2]
        working_df[new_col_name] = diff.dt.days

        null_count = working_df[new_col_name].isna().sum()
        if null_count > 0:
            warning = f"{null_count} row(s) produced NaT during datetime subtraction and are stored as NaN."

        message = (
            f"Computed '{col1}' - '{col2}' in days -> stored in '{new_col_name}'."
            + (f" Warning: {warning}" if warning else "")
        )

    # --- 6. Numeric branch ---
    else:
        for col in [col1, col2]:
            if not pd.api.types.is_numeric_dtype(working_df[col]):
                return _error_response(
                    f"Column '{col}' is not numeric (dtype: {working_df[col].dtype}). "
                    f"Set is_datetime=True for datetime columns."
                )

        if operation == "+":
            working_df[new_col_name] = working_df[col1] + working_df[col2]
        elif operation == "-":
            working_df[new_col_name] = working_df[col1] - working_df[col2]
        elif operation == "*":
            working_df[new_col_name] = working_df[col1] * working_df[col2]
        elif operation == "/":
            zero_count = (working_df[col2] == 0).sum()
            if zero_count > 0:
                warning = (
                    f"{zero_count} row(s) have zero in '{col2}'. "
                    f"Those rows will produce NaN or inf in '{new_col_name}'."
                )
            working_df[new_col_name] = working_df[col1] / working_df[col2]

        message = (
            f"Computed '{col1}' {operation} '{col2}' -> stored in '{new_col_name}'."
            + (f" Warning: {warning}" if warning else "")
        )

    return _success_response(message, working_df)
