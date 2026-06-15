"""
check_session_thread.py — Validates Plan A's core mechanism (V2 session
memory, Step 0): reusing a single LangGraph `thread_id` (the future
`session_id`) across multiple sequential `graph.invoke()` calls, with
`recent_questions` retrieved via `graph.get_state()` between calls.

Two things under test:
  1. `recent_questions` written by query 1's planner_node is readable via
     graph.get_state(config) and can be fed into query 2's initial_state.
  2. Query 2's execution state (plan/trace/current_step_index/status) is
     fresh and independent of query 1's — thread_id reuse doesn't bleed
     execution state across queries.

Run from the project root:

    python dev_checks/check_session_thread.py
"""

from pathlib import Path
import sys
import uuid

import pandas as pd

# Allow running this script directly regardless of working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.graph import build_graph


def _fresh_state(df: pd.DataFrame, query: str, run_id: str, recent_questions: list) -> dict:
    return {
        "query": query,
        "run_id": run_id,
        "original_df": df,
        "recent_questions": recent_questions,
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


def main():
    df = pd.read_csv(
        PROJECT_ROOT / "data" / "Sample - Superstore.csv",
        encoding="latin-1",
        parse_dates=["Order Date", "Ship Date"],
    )
    print(f"Loaded original_df: {df.shape}\n")

    # A single thread_id shared across both queries — stands in for the
    # future Streamlit-generated session_id.
    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 50}

    # ------------------------------------------------------------------
    # Query 1 — self-contained, no context needed
    # ------------------------------------------------------------------
    query1 = "What were the total sales in 2015?"
    run_id1 = str(uuid.uuid4())[:8]

    with build_graph() as graph:
        state1 = graph.invoke(_fresh_state(df, query1, run_id1, []), config=config)
        snapshot1 = graph.get_state(config)

    print(f"Query 1: {query1}")
    print(f"  status: {state1['status']}")
    print(f"  recent_questions: {state1['recent_questions']}")
    print(f"  plan: {' -> '.join(s.tool for s in state1['plan'])}")
    print(f"  current_step_index: {state1['current_step_index']} / {len(state1['plan'])}")
    print(f"  snapshot.next: {snapshot1.next}\n")

    assert state1["status"] == "running"  # clean success
    assert state1["recent_questions"] == [query1]
    assert snapshot1.next == ()
    assert snapshot1.values["recent_questions"] == [query1]

    # ------------------------------------------------------------------
    # Retrieve recent_questions for query 2 via get_state() — this is the
    # exact retrieval pipeline.py would do for Plan A.
    # ------------------------------------------------------------------
    prior_recent_questions = snapshot1.values["recent_questions"]

    # ------------------------------------------------------------------
    # Query 2 — also self-contained (mechanism check, not context-resolution)
    # ------------------------------------------------------------------
    query2 = "What were the total sales in 2016?"
    run_id2 = str(uuid.uuid4())[:8]

    with build_graph() as graph:
        state2 = graph.invoke(_fresh_state(df, query2, run_id2, prior_recent_questions), config=config)
        snapshot2 = graph.get_state(config)

    print(f"Query 2: {query2}")
    print(f"  status: {state2['status']}")
    print(f"  recent_questions: {state2['recent_questions']}")
    print(f"  plan: {' -> '.join(s.tool for s in state2['plan'])}")
    print(f"  current_step_index: {state2['current_step_index']} / {len(state2['plan'])}")
    print(f"  trace length: {len(state2['trace'])}")
    print(f"  run_id: {state2['run_id']}")
    print(f"  snapshot.next: {snapshot2.next}\n")

    # recent_questions threaded correctly across the reused thread_id
    assert state2["recent_questions"] == [query1, query2]

    # query 2's execution state is fresh/independent — not contaminated by
    # query 1's plan/trace/run_id
    assert state2["status"] == "running"
    assert state2["run_id"] == run_id2
    assert state2["current_step_index"] == len(state2["plan"])
    assert len(state2["trace"]) == len(state2["plan"])
    assert state2["final_df"] is not None
    assert state2["answer"] is not None
    assert snapshot2.next == ()

    print("PASS — thread_id reuse across sequential queries works correctly:")
    print("  - recent_questions threads correctly via get_state()")
    print("  - each query's execution state (plan/trace/current_step_index/run_id) is independent")


if __name__ == "__main__":
    main()
