from decimal import Decimal

import pytest
from pydantic import ValidationError

from adaa.semantic_layer.compare import (
    comparison_columns,
    comparison_lines,
    merge_rows,
    split_comparison,
)
from adaa.semantic_layer.compiler import CompileError
from adaa.semantic_layer.definitions import SemanticLayer, load
from adaa.semantic_layer.request import StructuredRequest

Y2018 = {"start": "2018-01-01", "end": "2018-12-31"}
Y2017 = {"start": "2017-01-01", "end": "2017-12-31"}


@pytest.fixture(scope="module")
def layer() -> SemanticLayer:
    return load()


def test_compare_needs_a_period() -> None:
    with pytest.raises(ValidationError, match="compare_to needs a period"):
        StructuredRequest.model_validate({"metric": "revenue", "compare_to": Y2017})


def test_split_gives_two_ordinary_forms(layer: SemanticLayer) -> None:
    form = StructuredRequest.model_validate(
        {
            "metric": "revenue",
            "dimensions": ["customer_state"],
            "period": Y2018,
            "compare_to": Y2017,
            "sort": {"by": "revenue"},
            "limit": 5,
        }
    )
    current, previous = split_comparison(form, layer)
    assert current.compare_to is None and current.limit == 5  # the asked period: top 5
    assert str(previous.period.start if previous.period else "") == "2017-01-01"
    assert previous.compare_to is None
    assert previous.sort is None and previous.limit is None  # every earlier row, to look up


def test_a_time_breakdown_is_refused(layer: SemanticLayer) -> None:
    form = StructuredRequest.model_validate(
        {"metric": "revenue", "dimensions": ["month"], "period": Y2018, "compare_to": Y2017}
    )
    with pytest.raises(CompileError, match="trend by month instead"):
        split_comparison(form, layer)


def test_rows_join_on_the_dimension_values() -> None:
    current = [("SP", Decimal(150)), ("RJ", Decimal(80)), ("AC", Decimal(5))]
    previous = [("RJ", Decimal(100)), ("SP", Decimal(100)), ("MG", Decimal(60))]
    assert merge_rows(current, previous, "BRL") == [
        ("SP", Decimal(150), Decimal(100), Decimal(50), Decimal("0.5")),
        ("RJ", Decimal(80), Decimal(100), Decimal(-20), Decimal("-0.2")),
        ("AC", Decimal(5), None, None, None),  # no earlier value: no change
    ]  # MG is only in the earlier period: rows follow the asked period


def test_no_breakdown_is_one_row() -> None:
    assert merge_rows([(Decimal(10),)], [(Decimal(8),)], "count") == [
        (Decimal(10), Decimal(8), Decimal(2), Decimal("0.25"))
    ]


def test_earlier_zero_has_no_change_pct() -> None:
    assert merge_rows([(Decimal(10),)], [(Decimal(0),)], "count") == [
        (Decimal(10), Decimal(0), Decimal(10), None)
    ]


def test_a_rate_changes_in_points_with_no_pct() -> None:
    rows = merge_rows([(Decimal("0.081"),)], [(Decimal("0.068"),)], "ratio")
    assert rows == [(Decimal("0.081"), Decimal("0.068"), Decimal("0.013"))]
    assert comparison_columns(["late_delivery_rate"], "ratio") == [
        "late_delivery_rate",
        "previous",
        "change",
    ]
    assert comparison_columns(["revenue"], "BRL")[-1] == "change_pct"


def test_explanation_names_the_earlier_period() -> None:
    form = StructuredRequest.model_validate(
        {"metric": "revenue", "period": Y2018, "compare_to": Y2017}
    )
    lines = comparison_lines(form, "BRL")
    assert lines[0] == "Compared with: 2017-01-01 to 2017-12-31."
    assert "change % = change / earlier period" in lines[1]
