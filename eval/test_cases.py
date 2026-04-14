"""
test_cases.py — 30 EvalCase definitions for the ADAA evaluation pipeline.

Each EvalCase has:
    id              : "Q01"–"Q30"
    query           : Natural language query sent to the pipeline
    ground_truth_fn : fn(df: pd.DataFrame) -> pd.DataFrame
                      Pure pandas computation on the raw Superstore DataFrame.
                      Column naming mirrors the tool layer convention:
                        groupby_aggregate output → {col}_{op}  (e.g. Sales_sum, Profit_mean)
                        extract_date_part year   → integer column named "Year"
                        extract_date_part quarter → string column "Q1"/"Q2"/... named "Quarter"
                        extract_date_part month  → full month name string, named "Month"
                        column_arithmetic days   → integer column named "shipping_days"
    compare_mode    : "value_only" | "full" | "ordered"
    tags            : labels for group-level reporting
    float_tol       : relative tolerance for numeric comparison (default 1 %)
    notes           : known risks or edge cases

Compare mode rationale
----------------------
value_only  — Scalar results (single number) or results where pipeline output wrapping
              is uncertain (e.g. Group 1 with no filter → no constant group column).
              Also used for time-based and derived-column queries where the planner
              chooses the new_col_name unpredictably.
              Comparison: sort all numeric cell values from each DataFrame, compare arrays.

full        — Multi-row unordered results. Shape + column set + values must all match.
              Rows are sorted by all columns before comparison.

ordered     — Multi-row ranked results (top-N). Shape + column set + positional values.
              Row order is preserved — rank 1 must be rank 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

import pandas as pd


@dataclass
class EvalCase:
    id: str
    query: str
    ground_truth_fn: Callable[[pd.DataFrame], pd.DataFrame]
    compare_mode: str          # "value_only" | "full" | "ordered"
    tags: List[str] = field(default_factory=list)
    float_tol: float = 0.01
    notes: str = ""


# ===========================================================================
# Group 1 — Simple Aggregation (Q01–Q05)
# No filter, no grouping dimension. Pipeline must aggregate entire DataFrame.
# The tool layer has no "aggregate all" tool — planner must use a workaround
# (group by a constant column). Output wrapping is uncertain.
# compare_mode: value_only — only the numeric result value matters.
# ===========================================================================

def _q01_gt(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"Sales_sum": [df["Sales"].sum()]})


def _q02_gt(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"Discount_mean": [df["Discount"].mean()]})


def _q03_gt(df: pd.DataFrame) -> pd.DataFrame:
    # Count of rows = total orders
    return pd.DataFrame({"Order ID_count": [len(df)]})


def _q04_gt(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"Profit_sum": [df["Profit"].sum()]})


def _q05_gt(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"Quantity_mean": [df["Quantity"].mean()]})


# ===========================================================================
# Group 2 — Filtering (Q06–Q10)
# Filter to one value then aggregate. Pipeline: filter → groupby on the now-
# constant filter column → aggregate.
# Output: 2 columns (filter label + agg value), 1 row.
# compare_mode: value_only — the numeric aggregate is what matters.
# ===========================================================================

def _q06_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Category"] == "Technology"]
    result = f.groupby("Category")["Sales"].sum().reset_index()
    return result.rename(columns={"Sales": "Sales_sum"})


def _q07_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Region"] == "West"]
    result = f.groupby("Region")["Profit"].sum().reset_index()
    return result.rename(columns={"Profit": "Profit_sum"})


def _q08_gt(df: pd.DataFrame) -> pd.DataFrame:
    # Count orders in Consumer segment
    f = df[df["Segment"] == "Consumer"]
    result = f.groupby("Segment")["Order ID"].count().reset_index()
    return result.rename(columns={"Order ID": "Order ID_count"})


def _q09_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Ship Mode"] == "Standard Class"]
    result = f.groupby("Ship Mode")["Sales"].sum().reset_index()
    return result.rename(columns={"Sales": "Sales_sum"})


def _q10_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["State"] == "California"]
    result = f.groupby("State")["Sales"].mean().reset_index()
    return result.rename(columns={"Sales": "Sales_mean"})


# ===========================================================================
# Group 3 — Grouping and Ranking (Q11–Q15)
# Standard groupby → aggregate → sort → top-N.
# Column names are fully predictable (no date parts or derived columns).
# compare_mode: ordered — row position encodes rank.
# ===========================================================================

def _q11_gt(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("State")["Sales"]
        .sum()
        .reset_index()
        .rename(columns={"Sales": "Sales_sum"})
        .sort_values("Sales_sum", ascending=False)
        .head(5)
        .reset_index(drop=True)
    )


def _q12_gt(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("Sub-Category")["Profit"]
        .sum()
        .reset_index()
        .rename(columns={"Profit": "Profit_sum"})
        .sort_values("Profit_sum", ascending=True)
        .head(5)
        .reset_index(drop=True)
    )


def _q13_gt(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("Ship Mode")["Sales"]
        .mean()
        .reset_index()
        .rename(columns={"Sales": "Sales_mean"})
        .sort_values("Sales_mean", ascending=False)
        .head(3)
        .reset_index(drop=True)
    )


def _q14_gt(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("Customer Name")["Sales"]
        .sum()
        .reset_index()
        .rename(columns={"Sales": "Sales_sum"})
        .sort_values("Sales_sum", ascending=False)
        .head(10)
        .reset_index(drop=True)
    )


def _q15_gt(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("Category")["Discount"]
        .mean()
        .reset_index()
        .rename(columns={"Discount": "Discount_mean"})
        .sort_values("Discount_mean", ascending=False)
        .head(1)
        .reset_index(drop=True)
    )


# ===========================================================================
# Group 4 — Time Based (Q16–Q20)
# All require extract_date_part. The planner chooses new_col_name freely
# (e.g. "Year", "order_year", "year") — we cannot predict it.
# compare_mode: value_only — numeric values only, column names ignored.
#
# Note on Q16/Q20: Year is an integer column → included in numeric extraction.
# The sorted numeric arrays will contain both year integers and sales/profit
# floats. Since year values (2014–2017) are always smaller than yearly totals
# (hundreds of thousands), the sorted order separates them cleanly.
# ===========================================================================

def _q16_gt(df: pd.DataFrame) -> pd.DataFrame:
    temp = df.copy()
    temp["Year"] = pd.to_datetime(temp["Order Date"]).dt.year
    return (
        temp.groupby("Year")["Sales"]
        .sum()
        .reset_index()
        .rename(columns={"Sales": "Sales_sum"})
    )


def _q17_gt(df: pd.DataFrame) -> pd.DataFrame:
    # Month names are strings (e.g. "November") — not numeric.
    # Only the order count is numeric, so value_only extracts just the count.
    temp = df.copy()
    temp["Month"] = pd.to_datetime(temp["Order Date"]).dt.month_name()
    return (
        temp.groupby("Month")["Order ID"]
        .count()
        .reset_index()
        .rename(columns={"Order ID": "Order ID_count"})
        .sort_values("Order ID_count", ascending=False)
        .head(1)
        .reset_index(drop=True)
    )


def _q18_gt(df: pd.DataFrame) -> pd.DataFrame:
    # Quarter is a string ("Q1"..."Q4") — not numeric.
    # Only Profit_sum values (4 rows) are extracted by value_only.
    temp = df.copy()
    temp["Quarter"] = "Q" + pd.to_datetime(temp["Order Date"]).dt.quarter.astype(str)
    return (
        temp.groupby("Quarter")["Profit"]
        .sum()
        .reset_index()
        .rename(columns={"Profit": "Profit_sum"})
    )


def _q19_gt(df: pd.DataFrame) -> pd.DataFrame:
    temp = df.copy()
    temp["Quarter"] = "Q" + pd.to_datetime(temp["Order Date"]).dt.quarter.astype(str)
    q1 = temp[temp["Quarter"] == "Q1"]
    result = q1.groupby("Quarter")["Sales"].sum().reset_index()
    return result.rename(columns={"Sales": "Sales_sum"})


def _q20_gt(df: pd.DataFrame) -> pd.DataFrame:
    temp = df.copy()
    temp["Year"] = pd.to_datetime(temp["Order Date"]).dt.year
    return (
        temp.groupby("Year")["Profit"]
        .sum()
        .reset_index()
        .rename(columns={"Profit": "Profit_sum"})
        .sort_values("Profit_sum", ascending=False)
        .head(1)
        .reset_index(drop=True)
    )


# ===========================================================================
# Group 5 — Multi Condition (Q21–Q24 scalar, Q25 ordered)
# Q21–Q24: two filter steps → single aggregate. compare_mode: value_only.
# Q25: filter → groupby → rank. compare_mode: ordered (Customer Name predictable).
# ===========================================================================

def _q21_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[(df["Category"] == "Furniture") & (df["Region"] == "West")]
    result = f.groupby("Category")["Sales"].sum().reset_index()
    return result.rename(columns={"Sales": "Sales_sum"})


def _q22_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[(df["Segment"] == "Consumer") & (df["State"] == "California")]
    result = f.groupby("Segment")["Order ID"].count().reset_index()
    return result.rename(columns={"Order ID": "Order ID_count"})


def _q23_gt(df: pd.DataFrame) -> pd.DataFrame:
    temp = df.copy()
    temp["Quarter"] = "Q" + pd.to_datetime(temp["Order Date"]).dt.quarter.astype(str)
    f = temp[(temp["Category"] == "Technology") & (temp["Quarter"] == "Q1")]
    result = f.groupby("Category")["Profit"].mean().reset_index()
    return result.rename(columns={"Profit": "Profit_mean"})


def _q24_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[(df["Category"] == "Office Supplies") & (df["Region"] == "East")]
    result = f.groupby("Category")["Sales"].sum().reset_index()
    return result.rename(columns={"Sales": "Sales_sum"})


def _q25_gt(df: pd.DataFrame) -> pd.DataFrame:
    f = df[df["Segment"] == "Consumer"]
    return (
        f.groupby("Customer Name")["Sales"]
        .sum()
        .reset_index()
        .rename(columns={"Sales": "Sales_sum"})
        .sort_values("Sales_sum", ascending=False)
        .head(5)
        .reset_index(drop=True)
    )


# ===========================================================================
# Group 6 — Derived Calculations (Q26–Q30)
# All compute shipping_days = (Ship Date - Order Date).dt.days.
# The planner picks new_col_name for shipping_days freely.
# compare_mode: value_only — numeric values only.
# ===========================================================================

def _add_shipping_days(df: pd.DataFrame) -> pd.DataFrame:
    temp = df.copy()
    temp["shipping_days"] = (
        pd.to_datetime(temp["Ship Date"]) - pd.to_datetime(temp["Order Date"])
    ).dt.days
    return temp


def _q26_gt(df: pd.DataFrame) -> pd.DataFrame:
    temp = _add_shipping_days(df)
    return pd.DataFrame({"shipping_days_mean": [temp["shipping_days"].mean()]})


def _q27_gt(df: pd.DataFrame) -> pd.DataFrame:
    temp = _add_shipping_days(df)
    return (
        temp.groupby("Category")["shipping_days"]
        .mean()
        .reset_index()
        .rename(columns={"shipping_days": "shipping_days_mean"})
        .sort_values("shipping_days_mean", ascending=False)
        .head(1)
        .reset_index(drop=True)
    )


def _q28_gt(df: pd.DataFrame) -> pd.DataFrame:
    temp = _add_shipping_days(df)
    return (
        temp.groupby("Ship Mode")["shipping_days"]
        .mean()
        .reset_index()
        .rename(columns={"shipping_days": "shipping_days_mean"})
        .sort_values("shipping_days_mean", ascending=True)
        .head(1)
        .reset_index(drop=True)
    )


def _q29_gt(df: pd.DataFrame) -> pd.DataFrame:
    temp = _add_shipping_days(df)
    west = temp[temp["Region"] == "West"]
    return pd.DataFrame({"shipping_days_mean": [west["shipping_days"].mean()]})


def _q30_gt(df: pd.DataFrame) -> pd.DataFrame:
    temp = _add_shipping_days(df)
    return (
        temp.groupby("State")["shipping_days"]
        .mean()
        .reset_index()
        .rename(columns={"shipping_days": "shipping_days_mean"})
        .sort_values("shipping_days_mean", ascending=False)
        .head(5)
        .reset_index(drop=True)
    )


# ===========================================================================
# TEST_CASES — ordered list of all 30 EvalCase objects
# ===========================================================================

TEST_CASES: List[EvalCase] = [
    # --- Group 1: Simple Aggregation ---
    EvalCase(
        id="Q01",
        query="What is the total sales across all orders?",
        ground_truth_fn=_q01_gt,
        compare_mode="value_only",
        tags=["aggregation"],
        notes="No filter → no constant group column. Pipeline may group by a multi-valued column.",
    ),
    EvalCase(
        id="Q02",
        query="What is the average discount given across all products?",
        ground_truth_fn=_q02_gt,
        compare_mode="value_only",
        tags=["aggregation"],
        notes="No filter. Same scalar-wrapping risk as Q01.",
    ),
    EvalCase(
        id="Q03",
        query="How many total orders are there in the dataset?",
        ground_truth_fn=_q03_gt,
        compare_mode="value_only",
        tags=["aggregation", "count"],
        notes="Count of rows. Pipeline column name for count is planner-dependent.",
    ),
    EvalCase(
        id="Q04",
        query="What is the total profit across all regions?",
        ground_truth_fn=_q04_gt,
        compare_mode="value_only",
        tags=["aggregation"],
        notes="No filter. Planner may or may not group by Region.",
    ),
    EvalCase(
        id="Q05",
        query="What is the average quantity ordered per transaction?",
        ground_truth_fn=_q05_gt,
        compare_mode="value_only",
        tags=["aggregation"],
        notes="No filter. Mean of Quantity column.",
    ),
    # --- Group 2: Filtering ---
    EvalCase(
        id="Q06",
        query="What are the total sales for the Technology category?",
        ground_truth_fn=_q06_gt,
        compare_mode="value_only",
        tags=["filter", "aggregation"],
    ),
    EvalCase(
        id="Q07",
        query="What is the total profit from the West region?",
        ground_truth_fn=_q07_gt,
        compare_mode="value_only",
        tags=["filter", "aggregation"],
    ),
    EvalCase(
        id="Q08",
        query="How many orders were placed in the Consumer segment?",
        ground_truth_fn=_q08_gt,
        compare_mode="value_only",
        tags=["filter", "count"],
        notes="Count query — planner picks the count column; value_only ignores name.",
    ),
    EvalCase(
        id="Q09",
        query="What is the total sales for Standard Class ship mode?",
        ground_truth_fn=_q09_gt,
        compare_mode="value_only",
        tags=["filter", "aggregation"],
    ),
    EvalCase(
        id="Q10",
        query="What is the average sales value for orders from California?",
        ground_truth_fn=_q10_gt,
        compare_mode="value_only",
        tags=["filter", "aggregation"],
    ),
    # --- Group 3: Grouping and Ranking ---
    EvalCase(
        id="Q11",
        query="Which are the top 5 states by total sales?",
        ground_truth_fn=_q11_gt,
        compare_mode="ordered",
        tags=["groupby", "rank", "top_n"],
        notes="Expected columns: State, Sales_sum. Row order = rank.",
    ),
    EvalCase(
        id="Q12",
        query="Which are the bottom 5 sub-categories by total profit?",
        ground_truth_fn=_q12_gt,
        compare_mode="ordered",
        tags=["groupby", "rank", "bottom_n"],
        notes="Bottom 5 = sort ascending. Expected columns: Sub-Category, Profit_sum.",
    ),
    EvalCase(
        id="Q13",
        query="Which 3 ship modes generate the highest average sales?",
        ground_truth_fn=_q13_gt,
        compare_mode="ordered",
        tags=["groupby", "rank", "top_n"],
        notes="Expected columns: Ship Mode, Sales_mean.",
    ),
    EvalCase(
        id="Q14",
        query="Which are the top 10 customers by total sales?",
        ground_truth_fn=_q14_gt,
        compare_mode="ordered",
        tags=["groupby", "rank", "top_n"],
        notes="Expected columns: Customer Name, Sales_sum.",
    ),
    EvalCase(
        id="Q15",
        query="Which product category has the highest average discount?",
        ground_truth_fn=_q15_gt,
        compare_mode="ordered",
        tags=["groupby", "rank", "top_n"],
        notes="Returns 1 row. Expected columns: Category, Discount_mean.",
    ),
    # --- Group 4: Time Based ---
    EvalCase(
        id="Q16",
        query="What is the total sales for each year?",
        ground_truth_fn=_q16_gt,
        compare_mode="value_only",
        tags=["date", "groupby", "aggregation"],
        notes="Year col name is planner-chosen. Year (int) + Sales_sum both numeric → 8 values total.",
    ),
    EvalCase(
        id="Q17",
        query="Which month has the highest number of orders across all years?",
        ground_truth_fn=_q17_gt,
        compare_mode="value_only",
        tags=["date", "groupby", "rank", "count"],
        notes=(
            "Month name is a string → only count is numeric. "
            "value_only extracts 1 numeric value (the count for the top month)."
        ),
    ),
    EvalCase(
        id="Q18",
        query="What is the total profit per quarter?",
        ground_truth_fn=_q18_gt,
        compare_mode="value_only",
        tags=["date", "groupby", "aggregation"],
        notes="Quarter is a string → only 4 Profit_sum values are numeric.",
    ),
    EvalCase(
        id="Q19",
        query="What are the total sales for Q1 across all years?",
        ground_truth_fn=_q19_gt,
        compare_mode="value_only",
        tags=["date", "filter", "aggregation"],
        notes="Single aggregate after filtering to Q1. Quarter string → 1 numeric value.",
    ),
    EvalCase(
        id="Q20",
        query="Which year had the highest total profit?",
        ground_truth_fn=_q20_gt,
        compare_mode="value_only",
        tags=["date", "groupby", "rank"],
        notes=(
            "Returns 1 row. Year (int) + Profit_sum both numeric → 2 values. "
            "Year values (2014-2017) are always smaller than annual profit totals."
        ),
    ),
    # --- Group 5: Multi Condition ---
    EvalCase(
        id="Q21",
        query="What is the total sales for Furniture in the West region?",
        ground_truth_fn=_q21_gt,
        compare_mode="value_only",
        tags=["filter", "multi_condition", "aggregation"],
        notes="Two filter steps then aggregate. Group col is Category (constant after filter).",
    ),
    EvalCase(
        id="Q22",
        query="How many orders were placed in the Consumer segment in California?",
        ground_truth_fn=_q22_gt,
        compare_mode="value_only",
        tags=["filter", "multi_condition", "count"],
        notes="Two filters + count. Count column name is planner-dependent.",
    ),
    EvalCase(
        id="Q23",
        query="What is the average profit for Technology products in Q1?",
        ground_truth_fn=_q23_gt,
        compare_mode="value_only",
        tags=["filter", "multi_condition", "date", "aggregation"],
        notes="Requires extract_date_part + two filters + aggregate.",
    ),
    EvalCase(
        id="Q24",
        query="What are the total sales for Office Supplies in the East region?",
        ground_truth_fn=_q24_gt,
        compare_mode="value_only",
        tags=["filter", "multi_condition", "aggregation"],
    ),
    EvalCase(
        id="Q25",
        query="Which are the top 5 customers by sales in the Consumer segment?",
        ground_truth_fn=_q25_gt,
        compare_mode="ordered",
        tags=["filter", "multi_condition", "groupby", "rank", "top_n"],
        notes="Expected columns: Customer Name, Sales_sum. Row order = rank.",
    ),
    # --- Group 6: Derived Calculations ---
    EvalCase(
        id="Q26",
        query="What is the average shipping time in days across all orders?",
        ground_truth_fn=_q26_gt,
        compare_mode="value_only",
        tags=["derived", "aggregation"],
        notes=(
            "Requires column_arithmetic(Ship Date - Order Date). "
            "Planner picks new_col_name for shipping days; value_only ignores it."
        ),
    ),
    EvalCase(
        id="Q27",
        query="Which product category has the longest average shipping time?",
        ground_truth_fn=_q27_gt,
        compare_mode="value_only",
        tags=["derived", "groupby", "rank"],
        notes="Returns 1 row. shipping_days col name planner-chosen → value_only.",
    ),
    EvalCase(
        id="Q28",
        query="Which ship mode has the shortest average shipping time?",
        ground_truth_fn=_q28_gt,
        compare_mode="value_only",
        tags=["derived", "groupby", "rank"],
        notes="Returns 1 row. Sort ascending (shortest first).",
    ),
    EvalCase(
        id="Q29",
        query="What is the average shipping time for orders from the West region?",
        ground_truth_fn=_q29_gt,
        compare_mode="value_only",
        tags=["derived", "filter", "aggregation"],
        notes="Filter to West then mean shipping days. Single numeric result.",
    ),
    EvalCase(
        id="Q30",
        query="Which are the top 5 states with the longest average shipping time?",
        ground_truth_fn=_q30_gt,
        compare_mode="value_only",
        tags=["derived", "groupby", "rank", "top_n"],
        notes=(
            "Returns 5 rows. shipping_days col name planner-chosen → value_only "
            "compares 5 sorted mean values (state label strings are excluded)."
        ),
    ),
]
