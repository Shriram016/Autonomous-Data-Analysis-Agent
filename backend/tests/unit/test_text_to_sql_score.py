"""The baseline's scoring rules (experiment, M2 step 3b) on small made-up answers."""

from typing import Any

import pytest

from adaa.evals.cases import EvalCase
from experiments.text_to_sql.run import BaselineResult
from experiments.text_to_sql.score import Row, judge, same_rows, same_value


def case(**fields: Any) -> EvalCase:
    base: dict[str, Any] = {"id": "c", "kind": "simple", "question": "q"}
    if "expected_error" not in fields:
        base["expected_sql"] = "SELECT 1"
    return EvalCase.model_validate(base | fields)


def result(rows: list[list[Any]] | None = None, **fields: Any) -> BaselineResult:
    base: dict[str, Any] = {
        "id": "c",
        "kind": "simple",
        "question": "q",
        "variant": "A",
        "sql": "SELECT 1",
        "cannot_answer": None,
        "rows": rows or [],
        "error": None,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "seconds": 0.0,
    }
    return BaselineResult.model_validate(base | fields)


@pytest.mark.parametrize(
    ("want", "got", "same"),
    [
        ("13221498.11", "13221498.11", True),  # money, exact
        ("13221498.11", "15843553.24", False),  # revenue with freight
        (93358, 99441, False),  # customer_id instead of the person
        ("0.06770000000000000000", "6.77", True),  # a rate as a percent the LLM rounded
        ("0.06770123", "0.0677012", True),  # long decimals: within 0.01 %
        ("0.00628513", "0.00680000", False),  # a small rate: 2 decimals would hide this
        ("12.4968", "12.5", True),  # the LLM's ROUND(x, 1)
        ("2017-03-01T00:00:00", "2017-03", True),  # a month as a date or as text
        ("2017-Q2", "2017-04-01", True),  # a quarter as a label or as its first day
        ("2017-Q2", "2017-07-01", False),
        ("SP", "SP", True),
        ("SP", "RJ", False),
    ],
)
def test_values(want: Any, got: Any, same: bool) -> None:
    assert same_value(want, got) is same


def test_rows_ignore_column_order_and_row_order_unless_sorted() -> None:
    want: list[Row] = [["SP", "5.00"], ["RJ", "3.00"]]
    assert same_rows(want, [["3.00", "RJ"], ["5.00", "SP"]], ordered=False)
    assert not same_rows(want, [["RJ", "3.00"], ["SP", "5.00"]], ordered=True)
    assert not same_rows(want, [["SP", "5.00"]], ordered=False)


def test_a_comparison_needs_both_period_values() -> None:
    compare = case(
        kind="compare",
        expected_form={
            "metric": "revenue",
            "period": {"start": "2018-01-01", "end": "2018-12-31"},
            "compare_to": {"start": "2017-01-01", "end": "2017-12-31"},
        },
    )
    want: list[Row] = [["7218125.12", "5962902.01", "1255223.11", "0.2105"]]
    two_rows = result([[2018, "7218125.12"], [2017, "5962902.01"]])
    assert judge(compare, want, two_rows) == (True, "both period values found")
    with_freight = result([[2018, "8600000.00"], [2017, "5962902.01"]])
    assert judge(compare, want, with_freight)[0] is False


def test_a_must_stop_case_needs_cannot_answer() -> None:
    stop = case(kind="must_stop", expected_error="value_not_found")
    assert judge(stop, None, result(cannot_answer="Paris is not a state", sql=None))[0]
    assert judge(stop, None, result([["0"]])) == (
        False,
        "answered instead of stopping (value_not_found)",
    )


def test_an_sql_error_is_wrong() -> None:
    simple = case(expected_form={"metric": "revenue"})
    assert judge(simple, [["1"]], result(error="sql_error")) == (False, "sql_error")
