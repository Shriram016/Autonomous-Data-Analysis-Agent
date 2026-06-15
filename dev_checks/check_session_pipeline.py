"""
check_session_pipeline.py — Standalone smoke test for run_pipeline()'s
session memory support (V2 session memory, Step 5).

Two checks:
  1. Two calls with the SAME session_id: recent_questions accumulates
     across calls, while each call's execution state (plan/trace/
     total_executions) reflects only that call's query.
  2. A call with session_id=None: auto-generates a session_id and starts
     with empty recent_questions (no prior checkpoint).

Run from the project root:

    python dev_checks/check_session_pipeline.py
"""

from pathlib import Path
import sys
import uuid

# Allow running this script directly regardless of working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.pipeline import run_pipeline


def check_session_memory_threading():
    print("=== Same session_id across two calls ===")

    session_id = str(uuid.uuid4())

    query1 = "What were the total sales in 2015?"
    result1 = run_pipeline(query1, session_id=session_id)

    print(f"Query 1: {query1}")
    print(f"  status: {result1['status']}")
    print(f"  session_id: {result1['session_id']}")
    print(f"  recent_questions: {result1['recent_questions']}")
    print(f"  plan: {' -> '.join(s.tool for s in result1['plan'])}\n")

    assert result1["status"] == "success"
    assert result1["session_id"] == session_id
    assert result1["recent_questions"] == [query1]

    query2 = "What were the total sales in 2016?"
    result2 = run_pipeline(query2, session_id=session_id)

    print(f"Query 2: {query2}")
    print(f"  status: {result2['status']}")
    print(f"  session_id: {result2['session_id']}")
    print(f"  recent_questions: {result2['recent_questions']}")
    print(f"  plan: {' -> '.join(s.tool for s in result2['plan'])}")
    print(f"  total_executions: {result2['total_executions']}\n")

    assert result2["status"] == "success"
    assert result2["session_id"] == session_id
    assert result2["recent_questions"] == [query1, query2]
    # Execution state reflects only query 2
    assert result2["query"] == query2
    assert result2["total_executions"] == len(result2["plan"])

    print("PASS\n")


def check_no_session_id():
    print("=== session_id=None auto-generates a fresh session ===")

    query = "What were the total sales in 2015?"
    result = run_pipeline(query)

    print(f"  status: {result['status']}")
    print(f"  session_id: {result['session_id']}")
    print(f"  recent_questions: {result['recent_questions']}\n")

    assert result["status"] == "success"
    assert result["session_id"] is not None
    assert result["recent_questions"] == [query]

    print("PASS\n")


def main():
    check_session_memory_threading()
    check_no_session_id()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
