"""Offline unit tests for all 10 tools in TOOL_REGISTRY."""

import pandas as pd
import pytest

from src.tools.tools import TOOL_REGISTRY
from src.tools.aggregate_column import aggregate_column
from src.tools.column_arithmetic import column_arithmetic
from src.tools.date_filter import date_filter
from src.tools.extract_date_part import extract_date_part
from src.tools.filter_by_condition import filter_by_condition
from src.tools.groupby_aggregate import groupby_aggregate
from src.tools.rename_column import rename_column
from src.tools.select_columns import select_columns
from src.tools.sort import sort
from src.tools.top_n import top_n


def test_registry_has_all_ten_tools():
    assert set(TOOL_REGISTRY) == {
        "date_filter", "filter_by_condition", "extract_date_part",
        "column_arithmetic", "groupby_aggregate", "sort", "top_n",
        "select_columns", "rename_column", "aggregate_column",
    }


# ---------------------------------------------------------------- filter_by_condition
def test_filter_object_is_case_insensitive(df):
    r = filter_by_condition(df, "Category", "object", "tech")
    assert r["status"] == "success"
    assert len(r["result"]) == 2


def test_filter_numeric_operator(df):
    r = filter_by_condition(df, "Sales", "numeric", 100, ">=")
    assert r["status"] == "success"
    assert sorted(r["result"]["Sales"]) == [100.0, 200.0]


def test_filter_bad_operator_and_column(df):
    assert filter_by_condition(df, "Sales", "numeric", 1, "~")["status"] == "error"
    assert filter_by_condition(df, "Nope", "object", "x")["status"] == "error"


# ---------------------------------------------------------------- date_filter
def test_date_filter_window_ends_at_max_date_by_default(df):
    r = date_filter(df, "Order Date", "1Y")
    assert r["status"] == "success"
    assert (pd.to_datetime(r["result"]["Order Date"]) <= pd.Timestamp("2023-12-31")).all()
    assert len(r["result"]) == 3  # all 2023 rows


def test_date_filter_explicit_end_date(df):
    r = date_filter(df, "Order Date", "1Y", end_date="2022-12-31")
    assert r["status"] == "success"
    assert len(r["result"]) == 2


def test_date_filter_bad_period_and_column(df):
    assert date_filter(df, "Order Date", "yesterday")["status"] == "error"
    assert date_filter(df, "Nope", "1Y")["status"] == "error"


# ---------------------------------------------------------------- extract_date_part
@pytest.mark.parametrize("part,expected", [
    ("year", 2023), ("month", "January"), ("quarter", "Q1"), ("day", 15),
])
def test_extract_date_part(df, part, expected):
    r = extract_date_part(df, "Order Date", part, "out")
    assert r["status"] == "success"
    assert r["result"]["out"].iloc[0] == expected


def test_extract_date_part_errors(df):
    assert extract_date_part(df, "Order Date", "decade", "out")["status"] == "error"
    assert extract_date_part(df, "Order Date", "year", "Sales")["status"] == "error"


# ---------------------------------------------------------------- column_arithmetic
def test_column_arithmetic_numeric(df):
    r = column_arithmetic(df, "Profit", "Sales", "/", "margin")
    assert r["status"] == "success"
    assert r["result"]["margin"].iloc[0] == pytest.approx(0.1)


def test_column_arithmetic_datetime_days(df):
    r = column_arithmetic(df, "Ship Date", "Order Date", "-", "days", is_datetime=True)
    assert r["status"] == "success"
    assert r["result"]["days"].iloc[0] == 3


def test_column_arithmetic_errors(df):
    assert column_arithmetic(df, "Sales", "Profit", "^", "x")["status"] == "error"
    assert column_arithmetic(df, "Sales", "Profit", "+", "Sales")["status"] == "error"
    assert column_arithmetic(df, "Ship Date", "Order Date", "+", "d", is_datetime=True)["status"] == "error"


# ---------------------------------------------------------------- groupby_aggregate
def test_groupby_aggregate_names_and_values(df):
    r = groupby_aggregate(df, "Category", {"Sales": "sum"})
    assert r["status"] == "success"
    out = r["result"].set_index("Category")["Sales_sum"]
    assert out["Tech"] == 300.0 and out["Office"] == 60.0


def test_groupby_aggregate_rejects_bad_op_for_dtype(df):
    assert groupby_aggregate(df, "Category", {"Category": "sum"})["status"] == "error"
    assert groupby_aggregate(df, "Category", {"Sales": "mode"})["status"] == "error"
    assert groupby_aggregate(df, "Nope", {"Sales": "sum"})["status"] == "error"


# ---------------------------------------------------------------- aggregate_column
def test_aggregate_column(df):
    r = aggregate_column(df, "Sales", "sum", "Sales_sum")
    assert r["status"] == "success"
    assert r["result"].shape == (1, 1)
    assert r["result"]["Sales_sum"].iloc[0] == 410.0


def test_aggregate_column_errors(df):
    assert aggregate_column(df, "Sales", "median", "x")["status"] == "error"
    assert aggregate_column(df, "Nope", "sum", "x")["status"] == "error"


# ---------------------------------------------------------------- sort / top_n
def test_sort_desc_then_top_n(df):
    s = sort(df, {"Sales": "desc"})
    assert s["status"] == "success"
    t = top_n(s["result"], 2)
    assert list(t["result"]["Sales"]) == [200.0, 100.0]


def test_sort_errors(df):
    assert sort(df, {"Sales": "up"})["status"] == "error"
    assert sort(df, {})["status"] == "error"
    assert sort(df, {"Nope": "asc"})["status"] == "error"


def test_top_n_does_not_sort_and_handles_large_n(df):
    assert list(top_n(df, 2)["result"]["Sales"]) == [100.0, 200.0]
    assert len(top_n(df, 999)["result"]) == len(df)


def test_top_n_rejects_non_positive(df):
    assert top_n(df, 0)["status"] == "error"
    assert top_n(df, "abc")["status"] == "error"


# ---------------------------------------------------------------- select / rename
def test_select_columns(df):
    r = select_columns(df, ["Sales", "Category"])
    assert r["status"] == "success"
    assert list(r["result"].columns) == ["Sales", "Category"]
    assert select_columns(df, ["Sales", "Nope"])["status"] == "error"


def test_rename_column(df):
    r = rename_column(df, {"Sales": "Revenue"})
    assert r["status"] == "success"
    assert "Revenue" in r["result"].columns and "Sales" not in r["result"].columns
    assert rename_column(df, {"Nope": "x"})["status"] == "error"


# ---------------------------------------------------------------- common contract
def test_tools_reject_empty_dataframe(df):
    empty = df.iloc[0:0]
    assert sort(empty, {"Sales": "asc"})["status"] == "error"
    assert top_n(empty, 1)["status"] == "error"
    assert select_columns(empty, ["Sales"])["status"] == "error"


def test_tools_do_not_mutate_input(df):
    before = df.copy(deep=True)
    filter_by_condition(df, "Sales", "numeric", 50, ">")
    extract_date_part(df, "Order Date", "year", "Y")
    sort(df, {"Sales": "asc"})
    rename_column(df, {"Sales": "R"})
    pd.testing.assert_frame_equal(df, before)
