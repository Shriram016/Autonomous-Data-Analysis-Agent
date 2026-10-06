# """
# compound_test_cases.py — Compound / multi-intent query cases for the ADAA eval pipeline.
#
# A compound query asks for two or more distinct results in a single question.
# These cases are kept separate from test_cases.py (single-intent, ground-truth-verified)
# because the expected pipeline behavior for compound queries is still being decided.
#
# No ground_truth_fn or compare_mode is assigned here — this file is a catalogue of
# queries only. Expected behavior and evaluation logic will be added once the handling
# strategy is confirmed.
#
# Taxonomy of compound patterns
# ------------------------------
# Type A — Two different scalars
#     Query asks for two different aggregate values (different metrics, different filters).
#     Example: "What are total sales AND total profit?"
#     Neither output is a breakdown of the other — they're parallel but independent.
#
# Type B — Scalar + breakdown  (potentially resolvable)
#     Query asks for an overall aggregate AND a grouped breakdown of the same metric.
#     Example: "What are total sales? Also break it down by region."
#     The breakdown subsumes the scalar — answering just the breakdown is sufficient.
#
# Type C — Two different grouped outputs
#     Query asks for groupby results on two different dimensions simultaneously.
#     Example: "Which states are most profitable AND which categories are most profitable?"
#     Cannot be returned in a single DataFrame without losing one dimension.
#
# Type D — Comparison across two slices
#     Query asks to compare two time periods, segments, or categories side by side.
#     Example: "Compare Q1 and Q2 sales."
#     Requires two separate filter+aggregate chains whose results are placed side by side.
#
# Type E — Filter + two aggregations
#     Query filters first, then asks for two different aggregates on the result.
#     Example: "For Technology orders, show total sales AND average discount."
#
# STATUS: Superseded.
#   - Type B and Type D cases moved to eval/test_cases2.py (Q31–Q37) with ground truth.
#   - Remaining truly compound cases (Type A, C, E) moved to eval/test_cases3.py.
#   - This file is kept for reference only.
# """
#
# from __future__ import annotations
#
# from dataclasses import dataclass, field
# from typing import List, Optional
#
#
# @dataclass
# class CompoundCase:
#     id: str
#     query: str
#     compound_type: str          # "A" | "B" | "C" | "D" | "E"
#     tags: List[str] = field(default_factory=list)
#     notes: str = ""
#     expected_behavior: Optional[str] = None   # filled in once strategy is decided
#
#
# # ===========================================================================
# # Type A — Two different scalars
# # ===========================================================================
#
# COMPOUND_CASES: List[CompoundCase] = [
#     CompoundCase(
#         id="CQ01",
#         query="What are the total sales and total profit across all orders?",
#         compound_type="A",
#         tags=["two_scalars", "aggregation"],
#         notes="Two different metrics, no filter, no grouping. Both are whole-dataset aggregates.",
#     ),
#     CompoundCase(
#         id="CQ02",
#         query="What is the average discount and average quantity per order?",
#         compound_type="A",
#         tags=["two_scalars", "aggregation"],
#         notes="Two different mean aggregates over the full dataset.",
#     ),
#     CompoundCase(
#         id="CQ03",
#         query="How many orders were placed in total, and how many unique customers placed them?",
#         compound_type="A",
#         tags=["two_scalars", "count"],
#         notes="Count of rows vs count of distinct values — two different operations.",
#     ),
#
#     # ===========================================================================
#     # Type B — Scalar + breakdown  (potentially resolvable by picking breakdown)
#     # ===========================================================================
#
#     CompoundCase(
#         id="CQ04",
#         query="What are total sales? Also break it down by region.",
#         compound_type="B",
#         tags=["scalar_plus_breakdown", "aggregation"],
#         notes="Breakdown by region subsumes the scalar total. Q32 from original test_cases.py.",
#     ),
#     CompoundCase(
#         id="CQ05",
#         query="What is the average discount overall and by customer segment?",
#         compound_type="B",
#         tags=["scalar_plus_breakdown", "aggregation"],
#         notes="Breakdown by segment subsumes the overall average. Q33 from original test_cases.py.",
#     ),
#     CompoundCase(
#         id="CQ06",
#         query="Show me total profit and also which states are most profitable.",
#         compound_type="B",
#         tags=["scalar_plus_breakdown", "rank"],
#         notes=(
#             "Scalar total profit + ranked state breakdown. "
#             "Ranked breakdown subsumes the total if all states are returned. Q34 originally."
#         ),
#     ),
#     CompoundCase(
#         id="CQ07",
#         query="What is the average order value per category and overall?",
#         compound_type="B",
#         tags=["scalar_plus_breakdown", "aggregation"],
#         notes="Per-category breakdown subsumes the overall average. Q35 from original test_cases.py.",
#     ),
#     CompoundCase(
#         id="CQ08",
#         query="What were total sales in 2017, and how did each region perform that year?",
#         compound_type="B",
#         tags=["scalar_plus_breakdown", "date", "aggregation"],
#         notes="Year-filtered scalar + year-filtered regional breakdown. Breakdown subsumes scalar.",
#     ),
#
#     # ===========================================================================
#     # Type C — Two different grouped outputs
#     # ===========================================================================
#
#     CompoundCase(
#         id="CQ09",
#         query="Which states are most profitable and which product categories are most profitable?",
#         compound_type="C",
#         tags=["two_grouped_outputs", "rank"],
#         notes="Two separate groupby dimensions (State, Category). Cannot merge into one DataFrame.",
#     ),
#     CompoundCase(
#         id="CQ10",
#         query="What is the total sales by region and by ship mode?",
#         compound_type="C",
#         tags=["two_grouped_outputs", "aggregation"],
#         notes=(
#             "Groupby Region and groupby Ship Mode independently — "
#             "a cross-tab would change the meaning."
#         ),
#     ),
#     CompoundCase(
#         id="CQ11",
#         query="Show me the top 5 customers by sales and the top 5 states by sales.",
#         compound_type="C",
#         tags=["two_grouped_outputs", "rank", "top_n"],
#         notes="Two top-5 lists on different dimensions. Incompatible shapes.",
#     ),
#
#     # ===========================================================================
#     # Type D — Comparison across two slices
#     # ===========================================================================
#
#     CompoundCase(
#         id="CQ12",
#         query="Compare total sales in 2016 versus 2017.",
#         compound_type="D",
#         tags=["comparison", "date"],
#         notes=(
#             "Two year-filtered aggregates placed side by side. "
#             "Could potentially be answered as groupby Year filtered to 2016/2017."
#         ),
#     ),
#     CompoundCase(
#         id="CQ13",
#         query="How do sales in the Consumer segment compare to the Corporate segment?",
#         compound_type="D",
#         tags=["comparison", "filter"],
#         notes=(
#             "Two segment-filtered aggregates. "
#             "Could be answered as groupby Segment filtered to those two values."
#         ),
#     ),
#     CompoundCase(
#         id="CQ14",
#         query="What were profits in Q1 versus Q3?",
#         compound_type="D",
#         tags=["comparison", "date"],
#         notes="Two quarter-filtered aggregates. Groupby Quarter filtered to Q1/Q3 may work.",
#     ),
#
#     # ===========================================================================
#     # Type E — Filter first, then two aggregations
#     # ===========================================================================
#
#     CompoundCase(
#         id="CQ15",
#         query="For Technology orders, what are the total sales and average discount?",
#         compound_type="E",
#         tags=["filter_then_two_agg", "aggregation"],
#         notes="Single filter (Technology), then two different aggregates on the result.",
#     ),
#     CompoundCase(
#         id="CQ16",
#         query="In the West region, how many orders were placed and what was the total profit?",
#         compound_type="E",
#         tags=["filter_then_two_agg", "count", "aggregation"],
#         notes="Single filter (West), then count + sum — two different operations.",
#     ),
#     CompoundCase(
#         id="CQ17",
#         query="For orders shipped via First Class, what is the average shipping time and total sales?",
#         compound_type="E",
#         tags=["filter_then_two_agg", "derived", "aggregation"],
#         notes="Filter (First Class) + column_arithmetic for shipping days + Sales sum.",
#     ),
# ]
