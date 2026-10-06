"""
test_cases2.py — Round 2 EvalCase definitions: pseudo-compound queries.

These queries *look* compound (they ask for two things) but are fully solvable
in a single pipeline plan because one result subsumes the other, or both can be
answered from a single group-by operation.

Sourced from compound_test_cases.py (CQ04, CQ05, CQ07, CQ08, CQ12, CQ13, CQ14).

IDs Q31–Q37.

Group 7 (Q31–Q35) — Breakdown subsumes scalar
    Query asks "overall X and breakdown by Y". A group-by on Y answers both.

Group 8 (Q36–Q37) — Comparison across two slices
    Query asks to compare two specific values. Filter to both + group-by answers it.
"""

from __future__ import annotations

import pandas as pd

from eval.test_cases import EvalCase


TEST_CASES_2: list[EvalCase] = [

    # -----------------------------------------------------------------------
    # Group 7 — Breakdown subsumes scalar (Q31–Q35)
    # -----------------------------------------------------------------------

    EvalCase(
        id="Q31",
        query="What are total sales? Also break it down by region.",
        ground_truth_fn=lambda df: (
            df.groupby("Region")["Sales"]
            .sum()
            .reset_index()
            .rename(columns={"Sales": "Sales_sum"})
        ),
        compare_mode="value_only",
        tags=["pseudo_compound", "groupby", "aggregation"],
        notes=(
            "Pipeline should group by Region and sum Sales. "
            "The regional breakdown subsumes the overall total."
        ),
    ),

    EvalCase(
        id="Q32",
        query="What is the average discount overall and by customer segment?",
        ground_truth_fn=lambda df: (
            df.groupby("Segment")["Discount"]
            .mean()
            .reset_index()
            .rename(columns={"Discount": "Discount_mean"})
        ),
        compare_mode="value_only",
        tags=["pseudo_compound", "groupby", "aggregation"],
        notes=(
            "Pipeline should group by Segment and mean Discount. "
            "The per-segment breakdown subsumes the overall average."
        ),
    ),

    EvalCase(
        id="Q33",
        query="What is the average order value per category and overall?",
        ground_truth_fn=lambda df: (
            df.groupby("Category")["Sales"]
            .mean()
            .reset_index()
            .rename(columns={"Sales": "Sales_mean"})
        ),
        compare_mode="value_only",
        tags=["pseudo_compound", "groupby", "aggregation"],
        notes=(
            "Pipeline should group by Category and mean Sales. "
            "Per-category breakdown subsumes the overall average."
        ),
    ),

    EvalCase(
        id="Q34",
        query="What were total sales in 2017, and how did each region perform that year?",
        ground_truth_fn=lambda df: (
            df.copy()
            .assign(**{"Order Date": lambda d: pd.to_datetime(d["Order Date"])})
            .pipe(lambda d: d[d["Order Date"].dt.year == 2017])
            .groupby("Region")["Sales"]
            .sum()
            .reset_index()
            .rename(columns={"Sales": "Sales_sum"})
        ),
        compare_mode="value_only",
        tags=["pseudo_compound", "date", "filter", "groupby", "aggregation"],
        notes=(
            "Filter to 2017 then group by Region + sum Sales. "
            "Regional breakdown subsumes the 2017 total."
        ),
    ),

    EvalCase(
        id="Q35",
        query="What is the total profit by ship mode and overall?",
        ground_truth_fn=lambda df: (
            df.groupby("Ship Mode")["Profit"]
            .sum()
            .reset_index()
            .rename(columns={"Profit": "Profit_sum"})
        ),
        compare_mode="value_only",
        tags=["pseudo_compound", "groupby", "aggregation"],
        notes=(
            "Group by Ship Mode and sum Profit. "
            "Per-ship-mode breakdown subsumes the overall total."
        ),
    ),

    # -----------------------------------------------------------------------
    # Group 8 — Comparison across two slices (Q36–Q37)
    # -----------------------------------------------------------------------

    EvalCase(
        id="Q36",
        query="Compare total sales in 2016 versus 2017.",
        ground_truth_fn=lambda df: (
            df.copy()
            .assign(**{"Order Date": lambda d: pd.to_datetime(d["Order Date"]),
                       "Year": lambda d: pd.to_datetime(d["Order Date"]).dt.year})
            .pipe(lambda d: d[d["Year"].isin([2016, 2017])])
            .groupby("Year")["Sales"]
            .sum()
            .reset_index()
            .rename(columns={"Sales": "Sales_sum"})
        ),
        compare_mode="value_only",
        tags=["pseudo_compound", "comparison", "date", "aggregation"],
        notes=(
            "Extract year, filter to [2016, 2017], group by Year, sum Sales. "
            "Returns 2-row DataFrame. value_only compares 4 numeric values "
            "(year integers + sales totals)."
        ),
    ),

    EvalCase(
        id="Q37",
        query="How do sales in the Consumer segment compare to the Corporate segment?",
        ground_truth_fn=lambda df: (
            df[df["Segment"].isin(["Consumer", "Corporate"])]
            .groupby("Segment")["Sales"]
            .sum()
            .reset_index()
            .rename(columns={"Sales": "Sales_sum"})
        ),
        compare_mode="value_only",
        tags=["pseudo_compound", "comparison", "filter", "aggregation"],
        notes=(
            "Filter to [Consumer, Corporate], group by Segment, sum Sales. "
            "Returns 2-row DataFrame."
        ),
    ),
]
