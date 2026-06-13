"""
check_graph.py — Standalone smoke test for src/core/graph.py
(build_graph() and the conditional edge / routing functions).

Three checks:
  1. Routing unit tests — call the _route_after_* functions directly with
     hand-built state dicts to confirm each branch (success/fail, more
     steps/last step, retries left/exhausted, cap hit).
  2. Param fixer recovery path — a small sub-graph (execute_step / param_fixer /
     replanner only) driven with a deliberately bad 2-step plan (bad column
     name), to confirm the real (Step 5) param_fixer corrects the bad column
     on the first retry and the sub-graph routes: execute_step (fail) ->
     param_fixer (fix) -> execute_step (success) -> execute_step (success) -> END.
  3. Happy path — the full compiled graph (build_graph()) run against a
     real query with a real LLM plan + execution + answer.

Run from the project root:

    python dev_checks/check_graph.py
"""

from pathlib import Path
import sys
import uuid

import pandas as pd
from langgraph.graph import StateGraph, END

# Allow running this script directly regardless of working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.state import PipelineState
from src.core.planner import PlanStep
from src.core.nodes import execute_step_node, param_fixer_node, replanner_node
from src.core.graph import (
    build_graph,
    _route_after_schema_gen,
    _route_after_planner,
    _route_after_execute_step,
    _route_after_replanner,
)
from src.config import MAX_RETRIES_PER_STEP


def _fresh_state(df: pd.DataFrame, plan_steps, run_id: str) -> PipelineState:
    return {
        "query": "What are total sales by category in the West region?",
        "run_id": run_id,
        "original_df": df,
        "schema": {},
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


# ---------------------------------------------------------------------------
# 1. Routing unit tests
# ---------------------------------------------------------------------------

def check_routing():
    print("=== Routing unit tests ===")

    # schema_gen
    assert _route_after_schema_gen({"status": "pending"}) == "planner"
    assert _route_after_schema_gen({"status": "error"}) == END

    # planner
    assert _route_after_planner({"status": "pending"}) == "execute_step"
    assert _route_after_planner({"status": "error"}) == END
    assert _route_after_planner({"status": "unsolvable"}) == END

    # execute_step — success, more steps left
    assert _route_after_execute_step({
        "status": "running", "current_step_index": 1, "plan": [1, 2],
        "total_executions": 1, "max_executions": 4, "retry_count": 0,
    }) == "execute_step"

    # execute_step — success, last step
    assert _route_after_execute_step({
        "status": "running", "current_step_index": 2, "plan": [1, 2],
        "total_executions": 2, "max_executions": 4, "retry_count": 0,
    }) == "answer_gen"

    # execute_step — fail, retries left
    assert _route_after_execute_step({
        "status": "error", "current_step_index": 0, "plan": [1, 2],
        "total_executions": 1, "max_executions": 4, "retry_count": 0,
    }) == "param_fixer"
    assert MAX_RETRIES_PER_STEP == 2  # sanity: assumptions below depend on this

    # execute_step — fail, retries exhausted -> replanner
    assert _route_after_execute_step({
        "status": "error", "current_step_index": 0, "plan": [1, 2],
        "total_executions": 3, "max_executions": 4, "retry_count": 2,
    }) == "replanner"

    # execute_step — fail, execution cap hit -> END (checked before retry_count)
    assert _route_after_execute_step({
        "status": "error", "current_step_index": 0, "plan": [1, 2],
        "total_executions": 4, "max_executions": 4, "retry_count": 0,
    }) == END

    # replanner
    assert _route_after_replanner({"status": "running"}) == "execute_step"
    assert _route_after_replanner({"status": "error"}) == END

    print("PASS\n")


# ---------------------------------------------------------------------------
# 2. Param fixer recovery path: execute_step (fail) -> param_fixer (fix) ->
#    execute_step (success) -> execute_step (success) -> END
# ---------------------------------------------------------------------------

def _build_execute_subgraph():
    graph = StateGraph(PipelineState)
    graph.add_node("execute_step", execute_step_node)
    graph.add_node("param_fixer", param_fixer_node)
    graph.add_node("replanner", replanner_node)

    graph.set_entry_point("execute_step")
    graph.add_conditional_edges(
        "execute_step",
        _route_after_execute_step,
        {
            "execute_step": "execute_step",
            "param_fixer": "param_fixer",
            "replanner": "replanner",
            "answer_gen": END,  # not part of this sub-graph
            END: END,
        },
    )
    graph.add_edge("param_fixer", "execute_step")
    graph.add_conditional_edges(
        "replanner", _route_after_replanner, {"execute_step": "execute_step", END: END}
    )
    return graph.compile()


def check_param_fixer_recovery(df: pd.DataFrame):
    print("=== Param fixer recovery path (bad column -> param_fixer fixes -> success) ===")

    bad_plan = [
        PlanStep(
            step=1,
            tool="filter_by_condition",
            parameters={"col_name": "Nonexistent Column", "col_type": "object", "val_to_filter": "West"},
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
    state = _fresh_state(df, bad_plan, run_id)

    sub_graph = _build_execute_subgraph()
    final_state = sub_graph.invoke(state, config={"recursion_limit": 25})

    print(f"final status: {final_state['status']}")
    print(f"final message: {final_state['message']}")
    print(f"retry_count: {final_state['retry_count']}")
    print(f"total_executions: {final_state['total_executions']}")
    print(f"trace length: {len(final_state['trace'])}")
    print(f"fixed step 1 parameters: {final_state['plan'][0].parameters}")

    assert final_state["status"] == "running"  # completed successfully, no error
    assert final_state["current_step_index"] == len(bad_plan)  # both steps completed
    assert final_state["retry_count"] == 0  # reset after the successful retry
    assert final_state["total_executions"] == 3  # 1 failed attempt + 2 successful
    assert len(final_state["trace"]) == 3
    assert final_state["trace"][0]["status"] == "error"
    assert final_state["trace"][1]["status"] == "success"
    assert final_state["trace"][2]["status"] == "success"
    assert final_state["plan"][0].parameters["col_name"] != "Nonexistent Column"
    assert final_state["final_df"] is not None

    print("PASS\n")


# ---------------------------------------------------------------------------
# 3. Happy path — full compiled graph, real LLM plan
# ---------------------------------------------------------------------------

def check_happy_path(df: pd.DataFrame):
    print("=== Happy path: full graph (real LLM plan) ===")

    run_id = str(uuid.uuid4())[:8]
    query = "What are the total sales in the West region?"
    state = _fresh_state(df, [], run_id)
    state["query"] = query
    state["schema"] = None  # let schema_gen_node populate it
    state["max_executions"] = 0

    with build_graph() as graph:
        final_state = graph.invoke(
            state,
            config={"configurable": {"thread_id": run_id}, "recursion_limit": 50},
        )

    print(f"final status: {final_state['status']}")
    print(f"plan: {' -> '.join(s.tool for s in final_state['plan'])}")
    print(f"current_step_index: {final_state['current_step_index']} / {len(final_state['plan'])}")
    print(f"total_executions: {final_state['total_executions']}")
    print(f"answer: {final_state['answer']}")

    assert final_state["status"] == "running"  # last node was answer_gen, not an error
    assert final_state["current_step_index"] == len(final_state["plan"])
    assert final_state["final_df"] is not None
    assert final_state["answer"] is not None

    print("PASS\n")


def main():
    df = pd.read_csv(
        PROJECT_ROOT / "data" / "Sample - Superstore.csv",
        encoding="latin-1",
        parse_dates=["Order Date", "Ship Date"],
    )
    print(f"Loaded original_df: {df.shape}\n")

    check_routing()
    check_param_fixer_recovery(df)
    check_happy_path(df)

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
