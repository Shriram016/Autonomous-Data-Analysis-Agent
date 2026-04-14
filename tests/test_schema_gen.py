from pathlib import Path
import sys

import pytest
import pandas as pd
import numpy as np

# Allow running this test file directly from the tests directory in debuggers/IDEs.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.schema_gen import generate_schema

SUPERSTORE_DATE_COLS = frozenset({"Order Date", "Ship Date"})

def test_generate_schema_from_valid_df():
    # Create a dummy DataFrame covering all targeted dtypes
    order_dates = pd.date_range("2024-01-01", periods=5)
    ship_dates = pd.date_range("2024-01-03", periods=5)
    df = pd.DataFrame({
        "num_col": [1, 2, 3, 4, 5],
        "float_col": [1.1, 2.2, 3.3, 4.4, 5.5],
        "Order Date": order_dates.astype(str),
        "Ship Date": ship_dates.astype(str),
        "string_col": ["alpha", "beta", "gamma", "delta", "epsilon"],
        "bool_col": [True, False, True, False, True],
        "null_col": [np.nan, np.nan, np.nan, np.nan, np.nan],
        "mixed_null_col": [10.0, np.nan, 30.0, np.nan, 50.0]
    })

    response = generate_schema(df, required_date_columns=SUPERSTORE_DATE_COLS)
    schema = response["result"]

    # Assert it returns a dict
    assert response["status"] == "success"
    assert response["message"] == "Schema generated successfully."
    assert isinstance(schema, dict)
    
    # Basic assertions
    assert "num_col" in schema
    assert "float_col" in schema
    assert "Order Date" in schema
    assert "Ship Date" in schema
    assert "string_col" in schema
    assert "null_col" in schema
    
    # Numeric column logic validation
    assert schema["num_col"]["min"] == 1.0
    assert schema["num_col"]["max"] == 5.0
    assert schema["num_col"]["median"] == 3.0
    assert schema["num_col"]["null_count"] == 0
    assert schema["num_col"]["null_percentage"] == 0.0
    assert schema["num_col"]["missingness_flag"] == "none"
    
    # Datetime logic validation
    assert schema["Order Date"]["min"] == str(order_dates.min())
    assert schema["Order Date"]["max"] == str(order_dates.max())
    assert schema["Ship Date"]["min"] == str(ship_dates.min())
    assert schema["Ship Date"]["max"] == str(ship_dates.max())
    
    # Categorical/Object logic validation
    assert "sample_values" in schema["string_col"]
    assert schema["string_col"]["unique_count"] == 5
    assert "alpha" in schema["string_col"]["sample_values"]
    
    # Complete null column validation
    assert schema["null_col"]["dtype"] == "null"
    assert schema["null_col"]["null_count"] == 5
    assert schema["null_col"]["null_percentage"] == 100.0
    assert schema["null_col"]["missingness_flag"] == "high"
    assert "warning" in schema["null_col"]
    
    # Mixed null column validation
    assert schema["mixed_null_col"]["null_count"] == 2
    assert schema["mixed_null_col"]["null_percentage"] == 40.0
    assert schema["mixed_null_col"]["missingness_flag"] == "high"
    assert schema["mixed_null_col"]["warning"] == "Column has high missingness"
    assert schema["mixed_null_col"]["min"] == 10.0
    assert schema["mixed_null_col"]["max"] == 50.0

def test_generate_schema_empty_df():
    # An empty dataframe should trigger the custom exception
    df = pd.DataFrame()
    response = generate_schema(df)
    assert response == {
        "status": "error",
        "message": "The provided DataFrame is empty. Cannot generate schema.",
        "result": None
    }

def test_generate_schema_invalid_input():
    # Only pandas Dataframes should be allowed
    invalid_input = [{"a": 1}, {"a": 2}]
    response = generate_schema(invalid_input)
    assert response == {
        "status": "error",
        "message": "Input must be a Pandas DataFrame.",
        "result": None
    }

def test_generate_schema_missing_required_date_columns():
    df = pd.DataFrame({
        "num_col": [1, 2, 3],
        "string_col": ["a", "b", "c"]
    })

    response = generate_schema(df, required_date_columns=SUPERSTORE_DATE_COLS)
    assert response["status"] == "error"
    assert "Missing required date column" in response["message"]
    assert response["result"] is None

def test_generate_schema_invalid_required_date_column_value():
    df = pd.DataFrame({
        "Order Date": ["2024-01-01", "not-a-date", "2024-01-03"],
        "Ship Date": ["2024-01-02", "2024-01-03", "2024-01-04"],
        "num_col": [1, 2, 3]
    })

    response = generate_schema(df, required_date_columns=SUPERSTORE_DATE_COLS)
    assert response["status"] == "error"
    assert "Invalid datetime values found" in response["message"]
    assert response["result"] is None

def test_generate_schema_uses_top_10_values_by_frequency_for_categorical_columns():
    df = pd.DataFrame({
        "Order Date": ["2024-01-01"] * 12,
        "Ship Date": ["2024-01-02"] * 12,
        "Category": [
            "zeta",
            "alpha", "alpha", "alpha",
            "beta", "beta",
            "gamma", "gamma", "gamma", "gamma",
            "delta",
            "epsilon"
        ]
    })

    response = generate_schema(df, required_date_columns=SUPERSTORE_DATE_COLS)
    sample_values = response["result"]["Category"]["sample_values"]

    assert sample_values[:5] == ["gamma", "alpha", "beta", "zeta", "delta"]

def test_generate_schema_adds_moderate_missingness_warning():
    df = pd.DataFrame({
        "Order Date": ["2024-01-01"] * 10,
        "Ship Date": ["2024-01-02"] * 10,
        "Sales": [10, 20, None, 40, 50, 60, 70, 80, None, 100]
    })

    response = generate_schema(df, required_date_columns=SUPERSTORE_DATE_COLS)
    sales_schema = response["result"]["Sales"]

    assert sales_schema["null_count"] == 2
    assert sales_schema["null_percentage"] == 20.0
    assert sales_schema["missingness_flag"] == "moderate"
    assert sales_schema["warning"] == "Column has moderate missingness"
