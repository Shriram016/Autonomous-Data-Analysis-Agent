"""
check_param_fixer.py — Standalone smoke test for src/core/param_fixer.py
(fix_params) and the param_fixer_node wrapper in src/core/nodes.py.

Covers:
  1. Real LLM call — bad column name gets corrected to a valid column.
  2. Fallback — GROQ_API_KEY missing -> step returned unchanged.
  3. Fallback — LLM returns invalid parameters twice -> step returned unchanged.
  4. End-to-end via param_fixer_node — plan updated, retry_count incremented.

Run from the project root:

    python dev_checks/check_param_fixer.py
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
from src.core.planner import PlanStep, validate_tool_parameters
from src.core import param_fixer
from src.core.param_fixer import fix_params, ParamFixResponse
from src.core.nodes import param_fixer_node


def _fresh_state(df: pd.DataFrame, plan_steps, run_id: str, message: str) -> PipelineState:
    return {
        "query": "Total sales in the West region",
        "run_id": run_id,
        "original_df": df,
        "schema": {},
        "plan": plan_steps,
        "max_executions": len(plan_steps) * 2,
        "state_store": {"original_df": df},
        "current_step_index": 0,
        "retry_count": 0,
        "total_executions": 1,
        "trace": [{"step": 1, "tool": plan_steps[0].tool, "status": "error", "message": message, "critic": "fail"}],
        "final_df": None,
        "status": "error",
        "message": message,
        "answer": None,
    }


def main():
    df = pd.read_csv(PROJECT_ROOT / "data" / "Sample - Superstore.csv", encoding="latin-1", parse_dates=["Order Date", "Ship Date"])
    print(f"Loaded original_df: {df.shape}\n")

    schema = {col: {"dtype": str(dtype)} for col, dtype in df.dtypes.items()}
    current_columns = {col: str(dtype) for col, dtype in df.dtypes.items()}

    # -----------------------------------------------------------------
    # 1. Real LLM call — bad column name gets corrected
    # -----------------------------------------------------------------
    print("=== 1. Real LLM call: bad column name ===")
    bad_step = PlanStep(
        step=1,
        tool="filter_by_condition",
        parameters={"col_name": "Sales Region", "col_type": "object", "val_to_filter": "West", "operator": "=="},
        input="original_df",
        output="step_1_output",
    )
    error_context = {
        "message": "Tool 'filter_by_condition' raised an unexpected error: 'Sales Region'",
        "current_columns": current_columns,
    }

    fixed_step = fix_params(bad_step, error_context, "Total sales in the West region", schema)

    is_valid, reason = validate_tool_parameters(fixed_step.tool, fixed_step.parameters)
    print(f"original col_name: {bad_step.parameters['col_name']}")
    print(f"fixed col_name:    {fixed_step.parameters.get('col_name')}")
    print(f"params valid:      {is_valid} ({reason})")

    assert fixed_step.tool == "filter_by_condition"
    assert fixed_step.input == "original_df"
    assert fixed_step.output == "step_1_output"
    assert is_valid, f"Corrected parameters invalid: {reason}"
    assert fixed_step.parameters.get("col_name") in current_columns, (
        f"Corrected col_name '{fixed_step.parameters.get('col_name')}' not in current columns."
    )
    print("PASS\n")

    # -----------------------------------------------------------------
    # 2. Fallback — GROQ_API_KEY missing
    # -----------------------------------------------------------------
    print("=== 2. Fallback: GROQ_API_KEY missing ===")
    original_key = param_fixer.GROQ_API_KEY
    param_fixer.GROQ_API_KEY = ""
    try:
        fixed_step = fix_params(bad_step, error_context, "Total sales in the West region", schema)
    finally:
        param_fixer.GROQ_API_KEY = original_key

    assert fixed_step.parameters == bad_step.parameters
    print("step returned unchanged")
    print("PASS\n")

    # -----------------------------------------------------------------
    # 3. Fallback — LLM returns invalid parameters twice
    # -----------------------------------------------------------------
    print("=== 3. Fallback: LLM returns invalid parameters twice ===")

    def _fake_call_groq(user_prompt, logger=None, run_id=None, error_context=None):
        return {"status": "success", "data": ParamFixResponse(parameters={"bogus_param": "x"})}

    original_call_groq = param_fixer._call_groq
    param_fixer._call_groq = _fake_call_groq
    try:
        fixed_step = fix_params(bad_step, error_context, "Total sales in the West region", schema)
    finally:
        param_fixer._call_groq = original_call_groq

    assert fixed_step.parameters == bad_step.parameters
    print("step returned unchanged after two invalid corrections")
    print("PASS\n")

    # -----------------------------------------------------------------
    # 4. End-to-end via param_fixer_node
    # -----------------------------------------------------------------
    print("=== 4. End-to-end via param_fixer_node ===")
    plan_steps = [bad_step]
    run_id = str(uuid.uuid4())[:8]
    state = _fresh_state(df, plan_steps, run_id, error_context["message"])

    update = param_fixer_node(state)
    state.update(update)

    is_valid, reason = validate_tool_parameters(
        state["plan"][0].tool, state["plan"][0].parameters
    )
    print(f"new parameters: {state['plan'][0].parameters}")
    print(f"params valid:   {is_valid} ({reason})")
    print(f"retry_count:    {state['retry_count']}")
    print(f"status:         {state['status']!r}")
    print(f"message:        {state['message']!r}")

    assert is_valid, f"Corrected parameters invalid: {reason}"
    assert state["retry_count"] == 1
    assert state["status"] == "running"
    assert state["message"] == ""
    print("PASS\n")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
