"""
End-to-end test runner for the Autonomous Data Analysis Agent (ADAA).
Runs all 5 target queries through the full pipeline and prints results.

Usage:
    python run_tests.py
"""

import sys
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.pipeline import run_pipeline


# ---------------------------------------------------------------------------
# Target Queries
# ---------------------------------------------------------------------------

QUERIES = [
    {
        "id": 1,
        "query": "Count of orders per month, sorted highest to lowest",
    },
    {
        "id": 2,
        "query": "What are the total sales of Furniture in California in Q1?",
    },
    {
        "id": 3,
        "query": "How long does shipping take? Are certain product categories shipped faster?",
    },
    {
        "id": 4,
        "query": "Is there a month-wise sales trend per product category?",
    },
    {
        "id": 5,
        "query": "Who are the top 10 customers by total sales in the last 3 months?",
    },
]


# ---------------------------------------------------------------------------
# Display Helpers
# ---------------------------------------------------------------------------

DIVIDER      = "=" * 70
THIN_DIVIDER = "-" * 70


def print_header(test_id: int, query: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  TEST {test_id}: {query}")
    print(DIVIDER)


def print_result(result: dict) -> None:
    status   = result["status"]
    run_id   = result["run_id"]
    message  = result["message"]
    trace    = result["trace"]
    final_df = result["final_df"]
    plan     = result["plan"]

    print(f"  run_id     : {run_id}")
    print(f"  status     : {status}")
    print(f"  message    : {message}")

    # Plan steps
    if plan:
        steps = " -> ".join(s.tool for s in plan)
        print(f"  plan       : {steps}")
    else:
        print(f"  plan       : None")

    # Execution trace summary
    print(f"  executions : {result['total_executions']}")
    if trace:
        print(f"  trace      :")
        for rec in trace:
            step    = rec.get("step", "?")
            tool    = rec.get("tool", "?")
            status_ = rec.get("status", "?")
            critic  = rec.get("critic", "?")
            shape   = rec.get("output_shape")
            shape_s = f"{shape[0]} rows × {shape[1]} cols" if shape else "no output"
            print(f"    step {step}: {tool:<25} | {status_:<7} | critic: {critic:<4} | {shape_s}")

    # Answer
    answer = result.get("answer")
    if answer:
        print(f"\n  answer:")
        print(f"    {answer}")

    # Final output preview
    if final_df is not None:
        print(f"\n  output shape : {final_df.shape[0]} rows × {final_df.shape[1]} cols")
        print(f"  columns      : {list(final_df.columns)}")
        print(f"\n  preview (top 5):")
        print(final_df.head(5).to_string(index=False))
    else:
        print(f"\n  output       : None")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{'=' * 70}")
    print(f"  ADAA — End-to-End Test Run")
    print(f"  {len(QUERIES)} queries")
    print(f"{'=' * 70}")

    passed = 0
    failed = 0

    for test in QUERIES:
        print_header(test["id"], test["query"])

        # Pipeline logs stream to console automatically via logger
        print(f"\n  [pipeline logs]")
        print(THIN_DIVIDER)
        result = run_pipeline(test["query"])
        print(THIN_DIVIDER)

        print(f"\n  [result]")
        print_result(result)

        if result["status"] == "success":
            passed += 1
        else:
            failed += 1

    # Summary
    print(f"\n{DIVIDER}")
    print(f"  SUMMARY: {passed}/{len(QUERIES)} passed   {failed}/{len(QUERIES)} failed")
    print(f"{DIVIDER}\n")
