"""
test_cases3.py — Round 3 EvalCase definitions: truly compound queries.

These queries ask for two or more distinct results that CANNOT be solved
in a single pipeline plan. The expected pipeline behavior is "unsolvable".

Sourced from compound_test_cases.py (CQ01, CQ02, CQ03, CQ06, CQ09, CQ10,
CQ11, CQ15, CQ16, CQ17).

IDs Q38–Q47.

Group 9 (Q38–Q40) — Two different scalars (Type A)
    Query asks for two different aggregate values. Neither subsumes the other.

Group 10 (Q41) — Scalar + ranked breakdown (Type B, truly compound)
    Unlike pseudo-compound B cases (test_cases2.py), the ranked subset does
    not subsume the scalar — they have incompatible shapes.

Group 11 (Q42–Q44) — Two different grouped outputs (Type C)
    Two groupby operations on different dimensions. Cannot merge into one DataFrame.

Group 12 (Q45–Q47) — Filter + two aggregations (Type E)
    Single filter followed by two different aggregate operations.
"""

from __future__ import annotations

from eval.test_cases import EvalCase


TEST_CASES_3: list[EvalCase] = [

    # -----------------------------------------------------------------------
    # Group 9 — Two different scalars (Q38–Q40)
    # -----------------------------------------------------------------------

    EvalCase(
        id="Q38",
        query="What are the total sales and total profit across all orders?",
        ground_truth_fn=None,
        compare_mode="value_only",
        tags=["compound", "two_scalars", "aggregation"],
        notes=(
            "Two different metrics (Sales sum, Profit sum), no grouping. "
            "Requires two separate aggregate_column calls — pipeline cannot chain them."
        ),
    ),

    EvalCase(
        id="Q39",
        query="What is the average discount and average quantity per order?",
        ground_truth_fn=None,
        compare_mode="value_only",
        tags=["compound", "two_scalars", "aggregation"],
        notes=(
            "Two different mean aggregates (Discount, Quantity) over the full dataset. "
            "Same issue as Q38 — two aggregate_column calls needed."
        ),
    ),

    EvalCase(
        id="Q40",
        query="How many orders were placed in total, and how many unique customers placed them?",
        ground_truth_fn=None,
        compare_mode="value_only",
        tags=["compound", "two_scalars", "count"],
        notes=(
            "Count of rows vs count of distinct Customer Name values. "
            "Two different operations with different semantics — no single tool handles both."
        ),
    ),

    # -----------------------------------------------------------------------
    # Group 10 — Scalar + ranked breakdown (Q41)
    # -----------------------------------------------------------------------

    EvalCase(
        id="Q41",
        query="Show me total profit and also which states are most profitable.",
        ground_truth_fn=None,
        compare_mode="value_only",
        tags=["compound", "scalar_plus_ranked", "aggregation", "rank"],
        notes=(
            "Scalar total profit (1 number) + ranked state list (N rows). "
            "Incompatible shapes — ranked top-N does not include the overall total."
        ),
    ),

    # -----------------------------------------------------------------------
    # Group 11 — Two different grouped outputs (Q42–Q44)
    # -----------------------------------------------------------------------

    EvalCase(
        id="Q42",
        query="Which states are most profitable and which product categories are most profitable?",
        ground_truth_fn=None,
        compare_mode="value_only",
        tags=["compound", "two_grouped_outputs", "rank"],
        notes=(
            "Two separate groupby dimensions (State, Category). "
            "Cannot merge into one DataFrame without losing one dimension."
        ),
    ),

    EvalCase(
        id="Q43",
        query="What is the total sales by region and by ship mode?",
        ground_truth_fn=None,
        compare_mode="value_only",
        tags=["compound", "two_grouped_outputs", "aggregation"],
        notes=(
            "Groupby Region and groupby Ship Mode independently. "
            "A cross-tab would change the meaning."
        ),
    ),

    EvalCase(
        id="Q44",
        query="Show me the top 5 customers by sales and the top 5 states by sales.",
        ground_truth_fn=None,
        compare_mode="value_only",
        tags=["compound", "two_grouped_outputs", "rank", "top_n"],
        notes=(
            "Two top-5 lists on different dimensions (Customer Name, State). "
            "Incompatible shapes — cannot be returned in one DataFrame."
        ),
    ),

    # -----------------------------------------------------------------------
    # Group 12 — Filter + two aggregations (Q45–Q47)
    # -----------------------------------------------------------------------

    EvalCase(
        id="Q45",
        query="For Technology orders, what are the total sales and average discount?",
        ground_truth_fn=None,
        compare_mode="value_only",
        tags=["compound", "filter_then_two_agg", "aggregation"],
        notes=(
            "Single filter (Category == Technology), then two different aggregates "
            "(Sales sum, Discount mean). Requires two aggregate_column calls after filter."
        ),
    ),

    EvalCase(
        id="Q46",
        query="In the West region, how many orders were placed and what was the total profit?",
        ground_truth_fn=None,
        compare_mode="value_only",
        tags=["compound", "filter_then_two_agg", "count", "aggregation"],
        notes=(
            "Single filter (Region == West), then count + sum. "
            "Two different operations on the filtered result."
        ),
    ),

    EvalCase(
        id="Q47",
        query="For orders shipped via First Class, what is the average shipping time and total sales?",
        ground_truth_fn=None,
        compare_mode="value_only",
        tags=["compound", "filter_then_two_agg", "derived", "aggregation"],
        notes=(
            "Filter (Ship Mode == First Class) + column_arithmetic for shipping days + Sales sum. "
            "Two different aggregates after filter, one requiring a derived column."
        ),
    ),
]
