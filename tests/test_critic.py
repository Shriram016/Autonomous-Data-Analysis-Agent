"""Offline unit tests for the 8 checks in the rule-based critic.

The critic validates a tool's OUTPUT DataFrame after each step (the plan itself
is validated earlier, by Pydantic and _validate_plan).
"""

import numpy as np
import pandas as pd

from src.core.planner import PlanStep
from src.critics.rule_based_critic import critique


def step(tool, **params):
    return PlanStep(step=1, tool=tool, parameters=params, input="original_df", output="out")


def run(s, result, input_df):
    return critique(s, {"status": "success"}, result, input_df)


def test_pass_on_valid_output(df):
    s = step("filter_by_condition", col_name="Sales", col_type="numeric", val_to_filter=50)
    assert run(s, df.iloc[:3], df) == {"status": "pass"}


# 1. not_none
def test_not_none(df):
    r = run(step("sort", sort_col={"Sales": "asc"}), None, df)
    assert r["status"] == "fail" and r["check"] == "not_none"


# 2. not_empty
def test_not_empty(df):
    r = run(step("sort", sort_col={"Sales": "asc"}), df.iloc[0:0], df)
    assert r["status"] == "fail" and r["check"] == "not_empty"


# 3. no_fully_empty_columns
def test_no_fully_empty_columns(df):
    bad = df.copy()
    bad["Sales"] = np.nan
    r = run(step("sort", sort_col={"Sales": "asc"}), bad, df)
    assert r["status"] == "fail" and r["check"] == "no_fully_empty_columns"


# 4. expected_columns (one case per tool family)
def test_expected_columns_preserving_tool_drops_column(df):
    r = run(step("sort", sort_col={"Sales": "asc"}), df.drop(columns=["Profit"]), df)
    assert r["check"] == "expected_columns"


def test_expected_columns_new_column_missing(df):
    s = step("extract_date_part", col_name="Order Date", part="year", new_col_name="Y")
    assert run(s, df, df)["check"] == "expected_columns"


def test_expected_columns_select_columns(df):
    s = step("select_columns", col_list=["Sales", "Profit"])
    assert run(s, df[["Sales"]], df)["check"] == "expected_columns"


def test_expected_columns_rename(df):
    s = step("rename_column", rename_map={"Sales": "Revenue"})
    assert run(s, df, df)["check"] == "expected_columns"


def test_expected_columns_groupby(df):
    s = step("groupby_aggregate", group_col="Category", agg_col={"Sales": "sum"})
    wrong = pd.DataFrame({"Category": ["Tech", "Furniture", "Office"], "Sales": [1, 2, 3]})
    assert run(s, wrong, df)["check"] == "expected_columns"


def test_expected_columns_aggregate_column(df):
    s = step("aggregate_column", col_name="Sales", operation="sum", new_col_name="Sales_sum")
    assert run(s, pd.DataFrame({"x": [1]}), df)["check"] == "expected_columns"


# 5. groupby_row_count
def test_groupby_row_count(df):
    s = step("groupby_aggregate", group_col="Category", agg_col={"Sales": "sum"})
    short = pd.DataFrame({"Category": ["Tech", "Office"], "Sales_sum": [1.0, 2.0]})
    r = run(s, short, df)
    assert r["status"] == "fail" and r["check"] == "groupby_row_count"


def test_groupby_row_count_passes_when_correct(df):
    s = step("groupby_aggregate", group_col="Category", agg_col={"Sales": "sum"})
    ok = pd.DataFrame({"Category": ["Tech", "Furniture", "Office"], "Sales_sum": [1.0, 2.0, 3.0]})
    assert run(s, ok, df) == {"status": "pass"}


# 6. top_n_rows
def test_top_n_rows(df):
    r = run(step("top_n", N=2), df.iloc[:4], df)
    assert r["status"] == "fail" and r["check"] == "top_n_rows"


# 7. date_filter_range
def test_date_filter_range(df):
    s = step("date_filter", col_name="Order Date", time_period="1Y", end_date="2022-12-31")
    r = run(s, df, df)  # includes 2023 rows, which are after end_date
    assert r["status"] == "fail" and r["check"] == "date_filter_range"


# 8. numeric_agg_columns
def test_numeric_agg_columns(df):
    s = step("groupby_aggregate", group_col="Category", agg_col={"Sales": "sum"})
    bad = pd.DataFrame({"Category": ["Tech", "Furniture", "Office"],
                        "Sales_sum": ["a", "b", "c"]})
    r = run(s, bad, df)
    assert r["status"] == "fail" and r["check"] == "numeric_agg_columns"


# Short-circuit order and crash safety
def test_first_failure_short_circuits(df):
    # None would also break later checks; the reported check must be not_none.
    assert run(step("top_n", N=1), None, df)["check"] == "not_none"


def test_critic_crash_is_reported_not_raised(df):
    s = step("sort", sort_col={"Sales": "asc"})
    r = critique(s, {}, df, input_df=None)  # input_df=None breaks expected_columns
    assert r["status"] == "fail" and r["check"] == "critic_crash"
