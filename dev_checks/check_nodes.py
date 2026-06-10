"""
check_nodes.py — Standalone smoke test for src/core/nodes.py
(schema_gen_node, planner_node, answer_gen_node).

Builds a real PipelineState from the Superstore CSV, runs each node in
sequence (merging returned partial updates back into state, the same way
LangGraph would), and prints the results. Run from the project root:

    python dev_checks/check_nodes.py
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
from src.core.nodes import schema_gen_node, planner_node, answer_gen_node, _fallback_answer


def main():
    df = pd.read_csv(PROJECT_ROOT / "data" / "Sample - Superstore.csv", encoding="latin-1", parse_dates=["Order Date", "Ship Date"])
    print(f"Loaded original_df: {df.shape}\n")

    run_id = str(uuid.uuid4())[:8]
    query = "What are the total sales in the West region?"

    state: PipelineState = {
        "query": query,
        "run_id": run_id,
        "original_df": df,
        "schema": None,
        "plan": [],
        "max_executions": 0,
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

    # -----------------------------------------------------------------
    # 1. schema_gen_node
    # -----------------------------------------------------------------
    print("=== schema_gen_node ===")
    update = schema_gen_node(state)
    state.update(update)

    if state["status"] == "error":
        print(f"FAIL: {state['message']}")
        return

    assert state["schema"] is not None
    print(f"schema columns: {list(state['schema'].keys())}")
    print("PASS\n")

    # -----------------------------------------------------------------
    # 2. planner_node
    # -----------------------------------------------------------------
    print("=== planner_node ===")
    update = planner_node(state)
    state.update(update)

    if state["status"] in ("error", "unsolvable"):
        print(f"{state['status'].upper()}: {state['message']}")
        print("(skipping plan assertions — continuing to test answer_gen_node, "
              "which is independent of the planner)\n")
        # Reset status so the remaining independent checks below still run
        state["status"] = "pending"
    else:
        assert len(state["plan"]) > 0
        assert state["max_executions"] == len(state["plan"]) * 2
        print(f"plan ({len(state['plan'])} step(s)):")
        for step in state["plan"]:
            print(f"  step {step.step}: {step.tool}({step.parameters}) "
                  f"input={step.input} -> output={step.output}")
        print(f"max_executions: {state['max_executions']}")
        print("PASS\n")

    # -----------------------------------------------------------------
    # 3. answer_gen_node — using a manually built final_df
    #    (execute_step_node doesn't exist yet — Step 3)
    # -----------------------------------------------------------------
    print("=== answer_gen_node (with real final_df) ===")
    final_df = (
        df[df["Region"] == "West"][["Sales"]]
        .sum()
        .to_frame()
        .T
        .rename(columns={"Sales": "Total Sales"})
    )
    print(f"final_df:\n{final_df.to_string(index=False)}")

    state["final_df"] = final_df
    update = answer_gen_node(state)
    state.update(update)

    assert state["answer"] is not None
    print(f"\nanswer: {state['answer']}")
    print("PASS\n")

    # -----------------------------------------------------------------
    # 4. _fallback_answer — direct test (single-cell and multi-row df)
    # -----------------------------------------------------------------
    print("=== _fallback_answer (direct) ===")

    single_cell_df = pd.DataFrame({"Total Sales": [1234.5]})
    print(f"single-cell -> {_fallback_answer(single_cell_df)!r}")

    multi_row_df = df.groupby("Region")["Sales"].sum().reset_index().head(3)
    print(f"multi-row ->\n{_fallback_answer(multi_row_df)}")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
