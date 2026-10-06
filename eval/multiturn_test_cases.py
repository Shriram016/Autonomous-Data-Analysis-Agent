"""
multiturn_test_cases.py — Multi-turn eval cases for session memory (V2 SS2).

Each MultiTurnEvalCase is an ordered sequence of Turns, run through
run_pipeline(turn.query, session_id=<shared session_id>) so that
`recent_questions` carries forward exactly as it would in a real
Streamlit session.

Only the FINAL turn of each case has a ground_truth_fn/compare_mode —
earlier turns exist purely to establish context for the final turn's
ambiguous follow-up (e.g. "What about 2015?"). Earlier turns are still
executed (so recent_questions gets populated) but their output is not
checked.

ground_truth_fn / compare_mode / float_tol follow the same conventions
as eval/test_cases.py (EvalCase) — pure pandas computation on the raw
Superstore DataFrame, "value_only" mode used throughout since these are
all single-number results.

Dataset year range: 2014-2017 (see eval/test_cases.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

import pandas as pd


@dataclass
class Turn:
    query: str
    ground_truth_fn: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = None
    compare_mode: Optional[str] = None   # "value_only" | "full" | "ordered"
    float_tol: float = 0.01


@dataclass
class MultiTurnEvalCase:
    id: str
    turns: List[Turn]
    tags: List[str] = field(default_factory=list)
    notes: str = ""


# ===========================================================================
# Pattern 1 — Year swap
# ===========================================================================

def _mt01_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[pd.to_datetime(df["Order Date"]).dt.year == 2015]
    return pd.DataFrame({"Sales_sum": [f["Sales"].sum()]})


def _mt02_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[pd.to_datetime(df["Order Date"]).dt.year == 2016]
    return pd.DataFrame({"Sales_sum": [f["Sales"].sum()]})


# ===========================================================================
# Pattern 2 — Category swap
# ===========================================================================

def _mt03_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Category"] == "Technology"]
    return pd.DataFrame({"Profit_sum": [f["Profit"].sum()]})


def _mt04_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Category"] == "Office Supplies"]
    return pd.DataFrame({"Profit_sum": [f["Profit"].sum()]})


# ===========================================================================
# Pattern 3 — Region swap
# ===========================================================================

def _mt05_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Region"] == "East"]
    return pd.DataFrame({"Discount_mean": [f["Discount"].mean()]})


def _mt06_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Region"] == "South"]
    return pd.DataFrame({"Discount_mean": [f["Discount"].mean()]})


# ===========================================================================
# Pattern 4 — Segment swap
# ===========================================================================

def _mt07_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Segment"] == "Corporate"]
    return pd.DataFrame({"Sales_sum": [f["Sales"].sum()]})


def _mt08_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Segment"] == "Home Office"]
    return pd.DataFrame({"Sales_sum": [f["Sales"].sum()]})


# ===========================================================================
# Pattern 5 — Metric swap (fixed filter: Office Supplies, 2014)
# ===========================================================================

def _mt09_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[
        (df["Category"] == "Office Supplies")
        & (pd.to_datetime(df["Order Date"]).dt.year == 2014)
    ]
    return pd.DataFrame({"Profit_sum": [f["Profit"].sum()]})


def _mt10_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[
        (df["Category"] == "Office Supplies")
        & (pd.to_datetime(df["Order Date"]).dt.year == 2014)
    ]
    return pd.DataFrame({"Quantity_sum": [f["Quantity"].sum()]})


# ===========================================================================
# Pattern 6 — Sub-Category swap
# ===========================================================================

def _mt11_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Sub-Category"] == "Chairs"]
    return pd.DataFrame({"Quantity_sum": [f["Quantity"].sum()]})


def _mt12_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Sub-Category"] == "Tables"]
    return pd.DataFrame({"Quantity_sum": [f["Quantity"].sum()]})


# ===========================================================================
# Pattern 7 — Year + Region swap (4-turn, anchor drops out of window)
# ===========================================================================

def _mt13_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[
        (pd.to_datetime(df["Order Date"]).dt.year == 2015)
        & (df["Region"] == "East")
    ]
    return pd.DataFrame({"Sales_sum": [f["Sales"].sum()]})


# ===========================================================================
# Pattern 8 — Category + Metric swap (4-turn, anchor drops out of window)
# ===========================================================================

def _mt14_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Category"] == "Office Supplies"]
    return pd.DataFrame({"Sales_sum": [f["Sales"].sum()]})


# ===========================================================================
# Pattern 9 — Multi-year synthesis (4-turn, final turn references all 3 prior)
# ===========================================================================

def _mt15_gt(df: pd.DataFrame) -> pd.DataFrame:
    temp = df.copy()
    temp["Year"] = pd.to_datetime(temp["Order Date"]).dt.year
    f = temp[temp["Year"].isin([2015, 2016, 2017])]
    return (
        f.groupby("Year")["Sales"]
        .sum()
        .reset_index()
        .rename(columns={"Sales": "Sales_sum"})
    )


# ===========================================================================
# Pattern 10 — Multi-region synthesis (4-turn)
# ===========================================================================

def _mt16_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Region"].isin(["West", "East", "South"])]
    return (
        f.groupby("Region")["Profit"]
        .sum()
        .reset_index()
        .rename(columns={"Profit": "Profit_sum"})
    )


# ===========================================================================
# Cases
# ===========================================================================

MULTITURN_TEST_CASES: List[MultiTurnEvalCase] = [
    # --- Pattern 1: Year swap ---------------------------------------------
    MultiTurnEvalCase(
        id="MT01",
        turns=[
            Turn(query="What were total sales in 2014?"),
            Turn(
                query="What about 2015?",
                ground_truth_fn=_mt01_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "year_swap", "2turn"],
        notes="Follow-up year reference resolved via recent_questions.",
    ),
    MultiTurnEvalCase(
        id="MT02",
        turns=[
            Turn(query="What were total sales in 2014?"),
            Turn(query="What about 2015?"),
            Turn(
                query="And 2016?",
                ground_truth_fn=_mt02_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "year_swap", "3turn"],
        notes="Two chained follow-ups; recent_questions must retain context across both.",
    ),

    # --- Pattern 2: Category swap -------------------------------------------
    MultiTurnEvalCase(
        id="MT03",
        turns=[
            Turn(query="What was the total profit for the Furniture category?"),
            Turn(
                query="What about Technology?",
                ground_truth_fn=_mt03_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "category_swap", "2turn"],
        notes="Follow-up category reference resolved via recent_questions.",
    ),
    MultiTurnEvalCase(
        id="MT04",
        turns=[
            Turn(query="What was the total profit for the Furniture category?"),
            Turn(query="What about Technology?"),
            Turn(
                query="And Office Supplies?",
                ground_truth_fn=_mt04_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "category_swap", "3turn"],
        notes="Two chained category follow-ups.",
    ),

    # --- Pattern 3: Region swap ----------------------------------------------
    MultiTurnEvalCase(
        id="MT05",
        turns=[
            Turn(query="What is the average discount in the West region?"),
            Turn(
                query="What about the East region?",
                ground_truth_fn=_mt05_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "region_swap", "2turn"],
        notes="Follow-up region reference resolved via recent_questions.",
    ),
    MultiTurnEvalCase(
        id="MT06",
        turns=[
            Turn(query="What is the average discount in the West region?"),
            Turn(query="What about the East region?"),
            Turn(
                query="And the South region?",
                ground_truth_fn=_mt06_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "region_swap", "3turn"],
        notes="Two chained region follow-ups.",
    ),

    # --- Pattern 4: Segment swap ----------------------------------------------
    MultiTurnEvalCase(
        id="MT07",
        turns=[
            Turn(query="What were total sales for the Consumer segment?"),
            Turn(
                query="What about the Corporate segment?",
                ground_truth_fn=_mt07_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "segment_swap", "2turn"],
        notes="Follow-up segment reference resolved via recent_questions.",
    ),
    MultiTurnEvalCase(
        id="MT08",
        turns=[
            Turn(query="What were total sales for the Consumer segment?"),
            Turn(query="What about the Corporate segment?"),
            Turn(
                query="And the Home Office segment?",
                ground_truth_fn=_mt08_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "segment_swap", "3turn"],
        notes="Two chained segment follow-ups.",
    ),

    # --- Pattern 5: Metric swap (fixed filter) --------------------------------
    MultiTurnEvalCase(
        id="MT09",
        turns=[
            Turn(query="What were total sales for Office Supplies in 2014?"),
            Turn(
                query="What about the profit for the same?",
                ground_truth_fn=_mt09_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "metric_swap", "2turn"],
        notes="Filter (Office Supplies, 2014) carried over; metric changes from sales to profit.",
    ),
    MultiTurnEvalCase(
        id="MT10",
        turns=[
            Turn(query="What were total sales for Office Supplies in 2014?"),
            Turn(query="What about the profit for the same?"),
            Turn(
                query="And the total quantity instead?",
                ground_truth_fn=_mt10_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "metric_swap", "3turn"],
        notes="Same filter carried across two metric-swap follow-ups.",
    ),

    # --- Pattern 6: Sub-Category swap ------------------------------------------
    MultiTurnEvalCase(
        id="MT11",
        turns=[
            Turn(query="How many units of Phones were sold in total?"),
            Turn(
                query="What about Chairs?",
                ground_truth_fn=_mt11_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "subcategory_swap", "2turn"],
        notes="Follow-up sub-category reference resolved via recent_questions.",
    ),
    MultiTurnEvalCase(
        id="MT12",
        turns=[
            Turn(query="How many units of Phones were sold in total?"),
            Turn(query="What about Chairs?"),
            Turn(
                query="What about Tables?",
                ground_truth_fn=_mt12_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "subcategory_swap", "3turn"],
        notes="Two chained sub-category follow-ups.",
    ),

    # --- Pattern 7: Year + Region swap (4-turn) --------------------------------
    MultiTurnEvalCase(
        id="MT13",
        turns=[
            Turn(query="What were total sales in 2014?"),
            Turn(query="What about 2015?"),
            Turn(query="Show me just the West region for that."),
            Turn(
                query="And the East region?",
                ground_truth_fn=_mt13_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "year_region_swap", "4turn"],
        notes=(
            "4-turn case. Turn 1 (anchor) drops out of 3-question window by turn 4. "
            "Planner must resolve 'East region' + carry forward 2015 + Sales sum "
            "from turns 2-3 only."
        ),
    ),

    # --- Pattern 8: Category + Metric swap (4-turn) -----------------------------
    MultiTurnEvalCase(
        id="MT14",
        turns=[
            Turn(query="What was the total profit for Furniture?"),
            Turn(query="What about Technology?"),
            Turn(query="What were the total sales instead?"),
            Turn(
                query="And for Office Supplies?",
                ground_truth_fn=_mt14_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "category_metric_swap", "4turn"],
        notes=(
            "4-turn case. Turn 1 (anchor) drops out of 3-question window by turn 4. "
            "Planner must resolve 'Office Supplies' + carry forward 'total sales' "
            "from turn 3."
        ),
    ),

    # --- Pattern 9: Multi-year synthesis (4-turn) --------------------------------
    MultiTurnEvalCase(
        id="MT15",
        turns=[
            Turn(query="Tell me sales numbers in 2017."),
            Turn(query="What about 2016?"),
            Turn(query="2015?"),
            Turn(
                query="Can you show the 3 years we discussed in a table?",
                ground_truth_fn=_mt15_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "synthesis", "4turn"],
        notes=(
            "4-turn case — synthesis pattern. Final turn references ALL 3 prior turns, "
            "not just the most recent. Planner must aggregate context from the entire "
            "3-question window (2017, 2016, 2015) and produce a grouped result."
        ),
    ),

    # --- Pattern 10: Multi-region synthesis (4-turn) ------------------------------
    MultiTurnEvalCase(
        id="MT16",
        turns=[
            Turn(query="What is the total profit in the West region?"),
            Turn(query="What about East?"),
            Turn(query="And South?"),
            Turn(
                query="Can you compare all 3 regions we discussed?",
                ground_truth_fn=_mt16_gt,
                compare_mode="value_only",
            ),
        ],
        tags=["multiturn", "synthesis", "4turn"],
        notes=(
            "4-turn case — synthesis pattern. Final turn references ALL 3 prior turns. "
            "Planner must gather West, East, South from the 3-question window and "
            "produce a grouped Profit sum result."
        ),
    ),
]
