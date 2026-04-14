from typing import Any, Dict, Iterable, Optional

import pandas as pd

def _get_missingness_flag(null_percentage: float) -> str:
    if null_percentage == 0:
        return "none"
    if null_percentage <= 5:
        return "low"
    if null_percentage <= 20:
        return "moderate"
    return "high"

def _error_response(message: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "message": message,
        "result": None
    }

def generate_schema(
    df: pd.DataFrame,
    required_date_columns: Optional[Iterable[str]] = None
) -> Dict[str, Any]:
    """
    Generate a dictionary schema representation of the DataFrame for the Planner LLM.
    
    The schema captures:
    - dtype for every column
    - min, max, median for numeric columns
    - min, max for datetime columns
    - A sample of unique values (up to 10) for object/categorical columns
    
    Returns:
        A standard response envelope containing status, message, and result.
    """
    if not isinstance(df, pd.DataFrame):
        return _error_response("Input must be a Pandas DataFrame.")
        
    if df.empty:
        return _error_response("The provided DataFrame is empty. Cannot generate schema.")

    required_date_columns = set(required_date_columns or [])
    missing_required_columns = required_date_columns.difference(df.columns)
    if missing_required_columns:
        missing_cols = ", ".join(sorted(missing_required_columns))
        return _error_response(
            f"Missing required date column(s): {missing_cols}"
        )

    schema: Dict[str, Any] = {}

    try:
        for column in df.columns:
            col_data = df[column]
            is_required_date_column = column in required_date_columns

            if is_required_date_column:
                try:
                    col_data = pd.to_datetime(col_data, errors="raise")
                except Exception as e:
                    return _error_response(
                        f"Invalid datetime values found in required date column '{column}': {str(e)}"
                    )

            col_type = col_data.dtype
            row_count = len(df)
            
            # Count missing values
            null_count = int(col_data.isna().sum())
            null_percentage = round((null_count / row_count) * 100, 2)
            missingness_flag = _get_missingness_flag(null_percentage)
            
            # If the column is completely empty, flag it and skip calculations
            if null_count == len(df):
                col_info = {
                    "dtype": "null",
                    "null_count": null_count,
                    "null_percentage": null_percentage,
                    "missingness_flag": missingness_flag,
                    "warning": "All values are missing"
                }
                schema[str(column)] = col_info
                continue
            
            # Get valid (non-null) data
            valid_data = col_data.dropna()
            
            col_info: Dict[str, Any] = {
                "dtype": str(col_type),
                "null_count": null_count,
                "null_percentage": null_percentage,
                "missingness_flag": missingness_flag
            }

            if missingness_flag == "moderate":
                col_info["warning"] = "Column has moderate missingness"
            elif missingness_flag == "high":
                col_info["warning"] = "Column has high missingness"

            # Numeric columns operations
            if pd.api.types.is_numeric_dtype(col_type):
                col_info["min"] = float(valid_data.min())
                col_info["max"] = float(valid_data.max())
                col_info["median"] = float(valid_data.median())
                
            # Datetime columns operations
            elif pd.api.types.is_datetime64_any_dtype(col_type):
                col_info["min"] = str(valid_data.min())
                col_info["max"] = str(valid_data.max())
                
            # Categorical, Object, String, or Boolean columns
            else:
                value_counts = valid_data.value_counts(dropna=True)
                
                # Use up to 10 most frequent values to provide a more representative sample.
                sample_values = value_counts.head(10).index.tolist()
                
                # Convert elements to string to ensure JSON serialization downstream
                col_info["sample_values"] = [str(val) for val in sample_values]
                col_info["unique_count"] = int(valid_data.nunique())
                
            schema[str(column)] = col_info

        return {
            "status": "success",
            "message": "Schema generated successfully.",
            "result": schema
        }

    except Exception as e:
        return _error_response(f"Failed to generate schema: {str(e)}")
