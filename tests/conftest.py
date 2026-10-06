"""Shared fixtures. All tests here run offline: no LLM, no network, no API keys."""

from pathlib import Path
import sys

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def df():
    """Small hand-built frame with string, numeric and date columns."""
    return pd.DataFrame({
        "Category": ["Tech", "Tech", "Furniture", "Office", "Office", "Office"],
        "Sales": [100.0, 200.0, 50.0, 10.0, 20.0, 30.0],
        "Profit": [10.0, 40.0, -5.0, 2.0, 4.0, 6.0],
        "Order Date": ["2023-01-15", "2023-06-20", "2023-12-31",
                       "2022-03-01", "2022-07-04", "2021-11-11"],
        "Ship Date": ["2023-01-18", "2023-06-22", "2024-01-04",
                      "2022-03-05", "2022-07-10", "2021-11-12"],
    })


@pytest.fixture(autouse=True)
def no_network_llm(monkeypatch):
    """Safety net: any test that accidentally reaches a Groq client fails loudly."""
    def boom(*a, **k):
        raise RuntimeError("Test tried to call the real Groq API. Mock it.")

    for mod in ("planner", "param_fixer", "replanner", "answer_generator"):
        try:
            m = __import__(f"src.core.{mod}", fromlist=["Groq"])
        except ImportError:
            continue
        if hasattr(m, "Groq"):
            monkeypatch.setattr(m, "Groq", boom)
