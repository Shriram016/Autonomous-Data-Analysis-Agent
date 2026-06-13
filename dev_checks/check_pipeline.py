"""
check_pipeline.py — Standalone smoke test for src/core/pipeline.py
(Step 8: run_pipeline() now invokes the V2 graph instead of
schema_gen()/plan()/loop_controller.run()).

One check:
  1. Happy path — a real query runs end-to-end through run_pipeline() and
     returns the same response shape as V1, with status "success" (mapped
     from the graph's final status="running").

(The "error"/"unsolvable" status passthrough is a one-line ternary already
exercised at the node level by check_replanner.py / check_graph.py.)

Run from the project root:

    python dev_checks/check_pipeline.py
"""

from pathlib import Path
import sys

# Allow running this script directly regardless of working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.pipeline import run_pipeline


def check_happy_path():
    print("=== Happy path: run_pipeline() end-to-end ===")

    query = "What are the total sales in the West region?"
    result = run_pipeline(query)

    print(f"status: {result['status']}")
    print(f"plan: {' -> '.join(s.tool for s in result['plan'])}")
    print(f"total_executions: {result['total_executions']}")
    print(f"trace length: {len(result['trace'])}")
    print(f"final_df shape: {result['final_df'].shape if result['final_df'] is not None else None}")
    print(f"answer: {result['answer']}")

    assert result["status"] == "success"  # mapped from graph's "running"
    assert result["schema"] is not None
    assert result["plan"]
    assert result["final_df"] is not None
    assert result["trace"]
    assert result["answer"] is not None

    print("PASS\n")


def main():
    check_happy_path()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
