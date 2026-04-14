from pathlib import Path
from typing import Any, Dict

import pandas as pd


# ---------------------------------------------------------------------------
# Dataset Path
# ---------------------------------------------------------------------------

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "Sample - Superstore.csv"

# Date columns that must be parsed as datetime
DATE_COLUMNS = ["Order Date", "Ship Date"]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_dataset() -> pd.DataFrame:
    """
    Loads the Sample Superstore dataset from the fixed project data path.

    Parses Order Date and Ship Date as datetime on load so the schema
    generator and tools receive correctly typed columns.

    Returns:
        Loaded DataFrame.

    Raises:
        FileNotFoundError : If the dataset file does not exist at DATA_PATH.
        ValueError        : If the loaded DataFrame is empty.
        Exception         : For any other read failure.
    """
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found at '{DATA_PATH}'. "
            "Ensure 'Sample - Superstore.csv' is in the project's data/ folder."
        )

    df = pd.read_csv(DATA_PATH, encoding="latin-1", parse_dates=DATE_COLUMNS)

    if df.empty:
        raise ValueError("Dataset loaded successfully but contains no rows.")

    return df
