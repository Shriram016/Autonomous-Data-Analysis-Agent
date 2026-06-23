"""
check_compound.py — Verify compound queries are rejected as unsolvable.

Run from project root:
    python dev_checks/check_compound.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.pipeline import run_pipeline

COMPOUND_QUERIES = [
    "How many unique customers do we have, and which regions have the most customers?",
    "What are total sales? Also break it down by region.",
    "What is the average discount overall and by customer segment?",
]

def main():
    all_passed = True
    for i, query in enumerate(COMPOUND_QUERIES, 1):
        print(f"\n[{i}] Query: {query}")
        result = run_pipeline(query)
        status = result.get("status")
        reason = result.get("reason") or result.get("message", "")
        print(f"    Status : {status}")
        print(f"    Reason : {reason}")
        if status == "unsolvable":
            print("    PASS")
        else:
            print(f"    FAIL — expected 'unsolvable', got '{status}'")
            all_passed = False

    print("\n" + ("=" * 50))
    print("All checks PASSED" if all_passed else "SOME CHECKS FAILED")
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
