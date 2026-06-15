"""
check_langfuse.py — Standalone smoke test for Langfuse Observability (V2 §3).

Runs one query end-to-end through run_pipeline() and prints the run_id,
session_id, and derived Langfuse trace_id so the trace can be opened
manually in the Langfuse Cloud dashboard to confirm:
  - The trace exists with the printed trace_id
  - session_id is set on the trace
  - "planner" and "answer_gen" generations are present with non-zero
    usage_details

If LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY are unset, trace_id_for_run()
returns None and this script just confirms the no-op path doesn't crash.

A param_fixer/replanner generation will land in the same trace
opportunistically if one of those nodes fires during the run — they use
the same trace_context derivation, so no separate query is needed to
verify that structurally.

Run from the project root:

    python dev_checks/check_langfuse.py
"""

from pathlib import Path
import sys

# Allow running this script directly regardless of working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.pipeline import run_pipeline
from src.utils.langfuse_helper import trace_id_for_run
from src.config import LANGFUSE_ENABLED


def check_simple_query():
    print("=== Simple query end-to-end ===")

    query = "What are the total sales in the West region?"
    result = run_pipeline(query)

    trace_id = trace_id_for_run(result["run_id"])

    print(f"  status: {result['status']}")
    print(f"  run_id: {result['run_id']}")
    print(f"  session_id: {result['session_id']}")
    print(f"  LANGFUSE_ENABLED: {LANGFUSE_ENABLED}")
    print(f"  langfuse trace_id: {trace_id}")

    assert result["status"] == "success"
    assert result["answer"] is not None

    if LANGFUSE_ENABLED:
        print(
            f"\n  Open https://us.cloud.langfuse.com and search for trace "
            f"id={trace_id} — confirm session_id={result['session_id']} and "
            f"'planner'/'answer_gen' generations with non-zero usage_details."
        )
    else:
        print("\n  LANGFUSE_ENABLED is False — no-op path exercised, no trace_id expected.")

    print("PASS\n")


def main():
    check_simple_query()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
