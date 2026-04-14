from typing import Any, Dict, Union

import pandas as pd

from src.utils.helpers import _error_response, _success_response


SUPPORTED_OPERATORS = {"==", "!=", ">", ">=", "<", "<="}
SUPPORTED_COL_TYPES = {"object", "numeric"}


def filter_by_condition(
    df: pd.DataFrame,
    col_name: str,
    col_type: str,
    val_to_filter: Union[str, int, float],
    operator: str = "==",
) -> Dict[str, Any]:
    """
    Filter rows by a single column value.

    Parameters
    ----------
    df            : Input DataFrame.
    col_name      : Column to filter on.
    col_type      : "object"  → case-insensitive exact string match (operator ignored).
                    "numeric" → numeric comparison using operator.
    val_to_filter : The value to match against. Single value only.
    operator      : Comparison operator for numeric columns.
                    Supported: "==", "!=", ">", ">=", "<", "<=".
                    Defaults to "==". Ignored when col_type is "object".

    Returns
    -------
    Standard response dict: {status, message, result}
    """

    # --- 1. Validate df ---
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a pandas DataFrame.")
    if df.empty:
        return _error_response("Input DataFrame is empty.")

    # --- 2. Validate col_type ---
    if col_type not in SUPPORTED_COL_TYPES:
        return _error_response(
            f"Invalid col_type '{col_type}'. Must be one of: {sorted(SUPPORTED_COL_TYPES)}."
        )

    # --- 3. Validate col_name exists ---
    if col_name not in df.columns:
        return _error_response(
            f"Column '{col_name}' not found in DataFrame. "
            f"Available columns: {list(df.columns)}"
        )

    # --- 4. Validate operator (only matters for numeric, but validate early) ---
    if operator not in SUPPORTED_OPERATORS:
        return _error_response(
            f"Invalid operator '{operator}'. "
            f"Supported operators: {sorted(SUPPORTED_OPERATORS)}."
        )

    working_df = df.copy()

    # --- 5. Object branch: case-insensitive exact match ---
    if col_type == "object":
        col_series = working_df[col_name].astype(str).str.lower().str.strip()
        search_val = str(val_to_filter).lower().strip()
        mask = col_series == search_val
        filter_desc = f"'{col_name}' == '{val_to_filter}' (case-insensitive)"

    # --- 6. Numeric branch: operator-based comparison ---
    else:
        if not pd.api.types.is_numeric_dtype(working_df[col_name]):
            return _error_response(
                f"col_type is 'numeric' but column '{col_name}' does not contain numeric data. "
                f"Actual dtype: {working_df[col_name].dtype}."
            )

        try:
            numeric_val = float(val_to_filter)
        except (ValueError, TypeError):
            return _error_response(
                f"val_to_filter '{val_to_filter}' could not be converted to a number "
                f"for numeric comparison."
            )

        op_map = {
            "==": working_df[col_name] == numeric_val,
            "!=": working_df[col_name] != numeric_val,
            ">":  working_df[col_name] >  numeric_val,
            ">=": working_df[col_name] >= numeric_val,
            "<":  working_df[col_name] <  numeric_val,
            "<=": working_df[col_name] <= numeric_val,
        }
        mask = op_map[operator]
        filter_desc = f"'{col_name}' {operator} {numeric_val}"

    # --- 7. Apply filter ---
    filtered_df = working_df[mask].reset_index(drop=True)

    # --- 8. Validate result is not empty ---
    if filtered_df.empty:
        return _error_response(
            f"No rows found where {filter_desc}. "
            f"Check the value or try a different filter."
        )

    return _success_response(
        f"Filtered {len(filtered_df)} rows where {filter_desc}.",
        filtered_df
    )
