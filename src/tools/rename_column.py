from typing import Any, Dict

import pandas as pd

from src.utils.helpers import _error_response, _success_response


def rename_column(
    df: pd.DataFrame,
    rename_map: Dict[str, str],
) -> Dict[str, Any]:
    """
    Rename one or more columns in the DataFrame.

    Parameters
    ----------
    df         : Input DataFrame.
    rename_map : Dict mapping old column names to new column names.
                 Key   = existing column name.
                 Value = desired new column name.
                 Example: {"Sales_sum": "Total Sales", "Profit_mean": "Avg Profit"}

    Rules
    -----
    - All old names must exist in df.
    - All new names must not already exist in df (collision check run before any rename).
    - Empty dict returns an error.

    Returns
    -------
    Standard response dict: {status, message, result}
    """

    # --- 1. Validate df ---
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a pandas DataFrame.")
    if df.empty:
        return _error_response("Input DataFrame is empty.")

    # --- 2. Validate rename_map is a non-empty dict ---
    if not isinstance(rename_map, dict) or not rename_map:
        return _error_response(
            "rename_map must be a non-empty dict mapping old names to new names. "
            "Example: {\"Sales_sum\": \"Total Sales\"}"
        )

    # --- 3. Validate all old names exist ---
    missing_old = [col for col in rename_map if col not in df.columns]
    if missing_old:
        return _error_response(
            f"Column(s) to rename not found in DataFrame: {missing_old}. "
            f"Available columns: {list(df.columns)}"
        )

    # --- 4. Validate new names don't collide with existing columns ---
    # Exclude cols that are being renamed (they will vacate their name)
    remaining_cols = set(df.columns) - set(rename_map.keys())
    collisions = [new for new in rename_map.values() if new in remaining_cols]
    if collisions:
        return _error_response(
            f"New column name(s) already exist in DataFrame: {collisions}. "
            f"Choose different names."
        )

    # --- 5. Validate no duplicate new names within the rename_map itself ---
    new_names = list(rename_map.values())
    if len(new_names) != len(set(new_names)):
        duplicates = [n for n in new_names if new_names.count(n) > 1]
        return _error_response(
            f"Duplicate new column name(s) in rename_map: {list(set(duplicates))}. "
            f"Each new name must be unique."
        )

    # --- 6. Rename ---
    result = df.rename(columns=rename_map).reset_index(drop=True)

    summary = ", ".join(f"'{old}' -> '{new}'" for old, new in rename_map.items())
    return _success_response(
        f"Renamed {len(rename_map)} column(s): {summary}.",
        result
    )
