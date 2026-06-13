"""
check_checkpointer.py — Standalone smoke test for SQLite checkpointing
(Step 7: src/core/graph.py build_graph() context manager + SqliteSaver).

Two checks:
  1. Checkpoints are persisted — running the graph with a thread_id writes
     state to CHECKPOINT_DB_PATH, queryable via graph.get_state(config).
  2. Crash/resume — a graph compiled with interrupt_after=["execute_step"]
     pauses after the first step (simulating a crash mid-plan). A fresh
     build_graph() (no interrupt) is then invoked with input=None and the
     same thread_id, which resumes from the checkpoint and completes.

Run from the project root:

    python dev_checks/check_checkpointer.py
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
from src.config import CHECKPOINT_DB_PATH


def _fresh_state(df: pd.DataFrame, query: str, run_id: str) -> dict:
    return {
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


def check_checkpoints_persisted(df: pd.DataFrame):
    print("=== Checkpoints persisted to CHECKPOINT_DB_PATH ===")

    run_id = str(uuid.uuid4())[:8]
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 50}
    query = "What are the total sales by category in the West region?"

    with build_graph() as graph:
        final_state = graph.invoke(_fresh_state(df, query, run_id), config=config)
        snapshot = graph.get_state(config)

    assert Path(CHECKPOINT_DB_PATH).exists(), "checkpoint db file was not created"
    assert snapshot.values["run_id"] == run_id
    assert snapshot.values["status"] == "running"  # completed without error
    assert final_state["answer"] is not None
    assert snapshot.next == ()  # graph finished, nothing left to run

    print(f"checkpoint db: {CHECKPOINT_DB_PATH}")
    print(f"plan: {' -> '.join(s.tool for s in final_state['plan'])}")
    print(f"answer: {final_state['answer']}")
    print("PASS\n")


def check_crash_resume(df: pd.DataFrame):
    print("=== Crash/resume: interrupt after execute_step, then resume ===")

    run_id = str(uuid.uuid4())[:8]
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 50}
    query = "What are the total profit and sales by category in the West region?"

    # 1. "Crash" — pause right after the first execute_step.
    with build_graph(interrupt_after=["execute_step"]) as graph:
        paused_state = graph.invoke(_fresh_state(df, query, run_id), config=config)
        paused_snapshot = graph.get_state(config)

    print(f"paused after step {paused_state['current_step_index']} "
          f"of {len(paused_state['plan'])}; trace length: {len(paused_state['trace'])}")
    print(f"next node(s) to run: {paused_snapshot.next}")

    assert paused_state["answer"] is None  # didn't reach answer_gen yet
    assert len(paused_state["trace"]) >= 1  # at least one step executed
    assert paused_snapshot.next != ()  # graph is paused, not finished

    # 2. "Resume" — fresh graph instance, same thread_id, input=None resumes
    #    from the last checkpoint instead of starting over.
    with build_graph() as graph:
        final_state = graph.invoke(None, config=config)
        final_snapshot = graph.get_state(config)

    print(f"resumed -> status: {final_state['status']}")
    print(f"resumed -> current_step_index: {final_state['current_step_index']} "
          f"/ {len(final_state['plan'])}")
    print(f"resumed -> answer: {final_state['answer']}")

    assert final_state["status"] == "running"  # completed without error
    assert final_state["current_step_index"] == len(final_state["plan"])
    assert final_state["final_df"] is not None
    assert final_state["answer"] is not None
    assert final_snapshot.next == ()

    print("PASS\n")


def main():
    df = pd.read_csv(
        PROJECT_ROOT / "data" / "Sample - Superstore.csv",
        encoding="latin-1",
        parse_dates=["Order Date", "Ship Date"],
    )
    print(f"Loaded original_df: {df.shape}\n")

    check_checkpoints_persisted(df)
    check_crash_resume(df)

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
