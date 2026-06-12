"""
check_replanner.py — Standalone smoke test for src/core/replanner.py
(replan) and the replanner_node wrapper in src/core/nodes.py.

Covers:
  1. Real LLM call — a plan that failed on an unrecoverable step
     (aggregate_column on a non-numeric column) gets replaced with a
     completely new, valid plan.
  2. Fallback — GROQ_API_KEY missing -> status "error".
  3. Fallback — LLM returns an invalid plan twice -> status "error".
  4. End-to-end via replanner_node — plan/state reset for a fresh run.

Run from the project root:

    python dev_checks/check_replanner.py
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
from src.core.planner import PlanStep, PlanResponse
from src.core.schema_gen import generate_schema
from src.utils.data_loader import DATE_COLUMNS
from src.core import replanner
from src.core.replanner import replan
from src.core.nodes import replanner_node


QUERY = "What is the total sales for the South region in 2015?"


def _fresh_state(df: pd.DataFrame, plan_steps, schema, run_id: str, message: str) -> PipelineState:
    failed_step = plan_steps[-1]
    trace = [
        {
            "step": 1, "tool": "extract_date_part",
            "parameters": {"col_name": "Order Date", "part": "year", "new_col_name": "Year"},
            "status": "success", "message": "ok",
            "output_shape": (9994, len(df.columns) + 1),
            "output_columns": list(df.columns) + ["Year"],
            "critic": "pass",
        },
        {
            "step": 2, "tool": "filter_by_condition",
            "parameters": {"col_name": "Region", "col_type": "object", "val_to_filter": "South", "operator": "=="},
            "status": "success", "message": "ok",
            "output_shape": (1620, len(df.columns) + 1),
            "output_columns": list(df.columns) + ["Year"],
            "critic": "pass",
        },
        {
            "step": failed_step.step, "tool": failed_step.tool,
            "parameters": failed_step.parameters,
            "status": "error", "message": message,
            "output_shape": None, "output_columns": None,
            "critic": "fail",
        },
    ]
    return {
        "query": QUERY,
        "run_id": run_id,
        "original_df": df,
        "schema": schema,
        "plan": plan_steps,
        "max_executions": len(plan_steps) * 2,
        "state_store": {"original_df": df, "step_1_output": df, "step_2_output": df},
        "current_step_index": len(plan_steps) - 1,
        "retry_count": 2,
        "total_executions": len(plan_steps) + 1,
        "trace": trace,
        "final_df": None,
        "status": "error",
        "message": message,
        "answer": None,
    }


def main():
    df = pd.read_csv(PROJECT_ROOT / "data" / "Sample - Superstore.csv", encoding="latin-1", parse_dates=["Order Date", "Ship Date"])
    print(f"Loaded original_df: {df.shape}\n")

    schema_result = generate_schema(df, required_date_columns=DATE_COLUMNS)
    assert schema_result["status"] == "success"
    schema = schema_result["result"]

    failed_step = PlanStep(
        step=3,
        tool="aggregate_column",
        parameters={"col_name": "Region", "operation": "sum", "new_col_name": "Region_sum"},
        input="step_2_output",
        output="step_3_output",
    )
    plan_steps = [
        PlanStep(step=1, tool="extract_date_part", parameters={"col_name": "Order Date", "part": "year", "new_col_name": "Year"}, input="original_df", output="step_1_output"),
        PlanStep(step=2, tool="filter_by_condition", parameters={"col_name": "Region", "col_type": "object", "val_to_filter": "South", "operator": "=="}, input="step_1_output", output="step_2_output"),
        failed_step,
    ]
    error_message = "Tool 'aggregate_column' raised an unexpected error: cannot aggregate non-numeric column 'Region'."

    error_context = {
        "failed_step": failed_step,
        "message": error_message,
        "trace": _fresh_state(df, plan_steps, schema, "x", error_message)["trace"],
    }

    # -----------------------------------------------------------------
    # 1. Real LLM call — unrecoverable step gets replaced with a new plan
    # -----------------------------------------------------------------
    print("=== 1. Real LLM call: unrecoverable step -> new plan ===")
    result = replan({"status": "success", "plan": plan_steps}, error_context, QUERY, schema)

    print(f"status: {result['status']}")
    assert result["status"] == "success", f"Expected success, got: {result}"

    new_plan = result["plan"]
    print(f"new plan: {' -> '.join(s.tool for s in new_plan)}")
    for s in new_plan:
        print(f"  step {s.step}: {s.tool} {s.parameters} | input={s.input} output={s.output}")

    assert new_plan[0].input == "original_df"
    # The new plan must not repeat the broken step (aggregate_column on "Region")
    assert not any(
        s.tool == "aggregate_column" and s.parameters.get("col_name") == "Region"
        for s in new_plan
    ), "Replanner repeated the broken step."
    print("PASS\n")

    # -----------------------------------------------------------------
    # 2. Fallback — GROQ_API_KEY missing
    # -----------------------------------------------------------------
    print("=== 2. Fallback: GROQ_API_KEY missing ===")
    original_key = replanner.GROQ_API_KEY
    replanner.GROQ_API_KEY = ""
    try:
        result = replan({"status": "success", "plan": plan_steps}, error_context, QUERY, schema)
    finally:
        replanner.GROQ_API_KEY = original_key

    print(f"status: {result['status']}")
    assert result["status"] == "error"
    print("PASS\n")

    # -----------------------------------------------------------------
    # 3. Fallback — LLM returns an invalid plan twice
    # -----------------------------------------------------------------
    print("=== 3. Fallback: LLM returns invalid plan twice ===")

    def _fake_call_groq(user_prompt, logger=None, run_id=None, error_context=None):
        return {
            "status": "success",
            "data": PlanResponse(status="success", plan=[
                PlanStep(step=1, tool="bogus_tool", parameters={}, input="original_df", output="step_1_output"),
            ]),
        }

    original_call_groq = replanner._call_groq
    replanner._call_groq = _fake_call_groq
    try:
        result = replan({"status": "success", "plan": plan_steps}, error_context, QUERY, schema)
    finally:
        replanner._call_groq = original_call_groq

    print(f"status: {result['status']}")
    print(f"message: {result['message']}")
    assert result["status"] == "error"
    print("PASS\n")

    # -----------------------------------------------------------------
    # 4. End-to-end via replanner_node
    # -----------------------------------------------------------------
    print("=== 4. End-to-end via replanner_node ===")
    run_id = str(uuid.uuid4())[:8]
    state = _fresh_state(df, plan_steps, schema, run_id, error_message)

    update = replanner_node(state)
    state.update(update)

    print(f"status: {state['status']!r}")
    print(f"new plan: {' -> '.join(s.tool for s in state['plan'])}")
    print(f"current_step_index: {state['current_step_index']}")
    print(f"retry_count: {state['retry_count']}")
    print(f"state_store keys: {list(state['state_store'].keys())}")
    print(f"max_executions: {state['max_executions']}")

    assert state["status"] == "running"
    assert state["message"] == ""
    assert state["current_step_index"] == 0
    assert state["retry_count"] == 0
    assert list(state["state_store"].keys()) == ["original_df"]
    assert state["max_executions"] == len(state["plan"]) * 2
    print("PASS\n")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
