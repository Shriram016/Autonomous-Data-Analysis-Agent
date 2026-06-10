"""
check_state.py — Standalone smoke test for src/core/state.py (PipelineState).

Builds a dummy PipelineState populated with real data (Superstore CSV +
a sample PlanStep) and confirms every field can be set and read back
correctly. Run from the project root:

    python dev_checks/check_state.py
"""

from pathlib import Path
import sys

import pandas as pd

# Allow running this script directly regardless of working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.state import PipelineState
from src.core.planner import PlanStep


def main():
    # Load the real dataset
    df = pd.read_csv(PROJECT_ROOT / "data" / "Sample - Superstore.csv", encoding="latin-1")
    print(f"Loaded original_df: {df.shape}")

    # Build a sample PlanStep (mirrors what the Planner would produce)
    step = PlanStep(
        step=1,
        tool="filter_rows",
        parameters={"column": "Region", "operator": "==", "value": "West"},
        input="original_df",
        output="step_1_output",
    )
    print(f"Built sample PlanStep: {step}")

    # Construct a fully populated PipelineState
    state: PipelineState = {
        "query": "What are total sales in the West region?",
        "run_id": "test-run-001",
        "original_df": df,

        "schema": None,

        "plan": [step],
        "max_executions": 2,

        "state_store": {"original_df": df},
        "current_step_index": 0,
        "retry_count": 0,
        "total_executions": 0,
        "trace": [],

        "final_df": None,
        "status": "pending",
        "message": "",
        "answer": None,
    }

    # Sanity checks — read every field back
    assert state["query"] == "What are total sales in the West region?"
    assert state["run_id"] == "test-run-001"
    assert state["original_df"].shape == df.shape
    assert state["schema"] is None
    assert isinstance(state["plan"], list) and isinstance(state["plan"][0], PlanStep)
    assert state["plan"][0].tool == "filter_rows"
    assert state["max_executions"] == 2
    assert "original_df" in state["state_store"]
    assert state["current_step_index"] == 0
    assert state["retry_count"] == 0
    assert state["total_executions"] == 0
    assert state["trace"] == []
    assert state["final_df"] is None
    assert state["status"] == "pending"
    assert state["message"] == ""
    assert state["answer"] is None

    print("\nAll PipelineState fields set and read back correctly.")
    print(f"Field count: {len(state)} / {len(PipelineState.__annotations__)}")
    print("PASS")


if __name__ == "__main__":
    main()
