"""
check_execute_step.py — Standalone smoke test for src/core/nodes.py
(execute_step_node).

Builds a real PipelineState from the Superstore CSV with a 2-step plan,
then drives execute_step_node in a loop (merging returned partial updates
back into state, the same way LangGraph would) until the plan completes.
Also exercises the failure path (bad parameters) and the out-of-range
guard. Run from the project root:

    python dev_checks/check_execute_step.py
"""

from pathlib import Path
import sys
import uuid

import pandas as pd

# Allow running this script directly regardless of working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.state import PipelineState
from src.core.planner import PlanStep
from src.core.nodes import execute_step_node


def _fresh_state(df: pd.DataFrame, plan_steps, run_id: str) -> PipelineState:
    return {
        "query": "What are total sales by category in the West region?",
        "run_id": run_id,
        "original_df": df,
        "schema": None,
        "plan": plan_steps,
        "max_executions": len(plan_steps) * 2,
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


def main():
    df = pd.read_csv(PROJECT_ROOT / "data" / "Sample - Superstore.csv", encoding="latin-1", parse_dates=["Order Date", "Ship Date"])
    print(f"Loaded original_df: {df.shape}\n")

    # -----------------------------------------------------------------
    # 1. Happy path — 2-step plan run to completion
    # -----------------------------------------------------------------
    print("=== Happy path: 2-step plan ===")
    plan_steps = [
        PlanStep(
            step=1,
            tool="filter_by_condition",
            parameters={"col_name": "Region", "col_type": "object", "val_to_filter": "West"},
            input="original_df",
            output="step_1_output",
        ),
        PlanStep(
            step=2,
            tool="groupby_aggregate",
            parameters={"group_col": "Category", "agg_col": {"Sales": "sum"}},
            input="step_1_output",
            output="step_2_output",
        ),
    ]

    run_id = str(uuid.uuid4())[:8]
    state = _fresh_state(df, plan_steps, run_id)

    while state["current_step_index"] < len(state["plan"]):
        update = execute_step_node(state)
        state.update(update)

        assert state["status"] != "error", f"Unexpected failure: {state['message']}"

    assert state["current_step_index"] == 2
    assert state["retry_count"] == 0
    assert state["total_executions"] == 2
    assert len(state["trace"]) == 2
    assert "step_1_output" in state["state_store"]
    assert "step_2_output" in state["state_store"]
    assert state["final_df"] is not None
    assert state["final_df"].shape[0] == 3  # 3 categories

    print(f"trace[0]: status={state['trace'][0]['status']}, critic={state['trace'][0]['critic']}, "
          f"output_shape={state['trace'][0]['output_shape']}")
    print(f"trace[1]: status={state['trace'][1]['status']}, critic={state['trace'][1]['critic']}, "
          f"output_shape={state['trace'][1]['output_shape']}")
    print(f"final_df:\n{state['final_df'].to_string(index=False)}")
    print("PASS\n")

    # -----------------------------------------------------------------
    # 2. Failure path — step with a bad column name
    # -----------------------------------------------------------------
    print("=== Failure path: bad column name ===")
    bad_plan = [
        PlanStep(
            step=1,
            tool="filter_by_condition",
            parameters={"col_name": "Nonexistent Column", "col_type": "object", "val_to_filter": "West"},
            input="original_df",
            output="step_1_output",
        ),
    ]

    run_id = str(uuid.uuid4())[:8]
    state = _fresh_state(df, bad_plan, run_id)

    update = execute_step_node(state)
    state.update(update)

    assert state["status"] == "error"
    assert "Nonexistent Column" in state["message"]
    assert state["current_step_index"] == 0  # unchanged — no retry yet
    assert state["total_executions"] == 1
    assert len(state["trace"]) == 1
    assert "step_1_output" not in state["state_store"]  # not advanced
    assert state["final_df"] is None

    print(f"status: {state['status']}")
    print(f"message: {state['message']}")
    print("PASS\n")

    # -----------------------------------------------------------------
    # 3. Out-of-range guard
    # -----------------------------------------------------------------
    print("=== Out-of-range guard ===")
    state = _fresh_state(df, plan_steps, str(uuid.uuid4())[:8])
    state["current_step_index"] = 99

    update = execute_step_node(state)
    state.update(update)

    assert state["status"] == "error"
    assert "out of range" in state["message"]

    print(f"status: {state['status']}")
    print(f"message: {state['message']}")
    print("PASS\n")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
