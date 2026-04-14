"""
check_gt.py — Quick ground truth checker.

Set QUERY to any of the 30 eval queries, run this file,
and it prints the expected output DataFrame for that query.
"""

import pandas as pd
from eval.test_cases import TEST_CASES

# ---------------------------------------------------------------------------
# Set your query here
# ---------------------------------------------------------------------------

QUERY = "Which are the top 5 states by total sales?"

# ---------------------------------------------------------------------------
# Lookup and run
# ---------------------------------------------------------------------------

df = pd.read_csv("data/Sample - Superstore.csv", encoding="latin-1")

match = next((c for c in TEST_CASES if c.query == QUERY), None)

if match is None:
    print(f"No test case found for query:\n  '{QUERY}'")
    print("\nAvailable queries:")
    for c in TEST_CASES:
        print(f"  [{c.id}] {c.query}")
else:
    result = match.ground_truth_fn(df)
    print(f"[{match.id}] {match.query}")
    print(f"Compare mode : {match.compare_mode}")
    print(f"Shape        : {result.shape}")
    print()
    print(result.to_string(index=False))
