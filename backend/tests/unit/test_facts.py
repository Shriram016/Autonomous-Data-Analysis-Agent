from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from adaa.agent.facts import build_facts, format_number
from adaa.semantic_layer.definitions import SemanticLayer, load
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult


@pytest.fixture(scope="module")
def layer() -> SemanticLayer:
    return load()


def result(*rows: tuple[object, ...]) -> QueryResult:
    return QueryResult(
        columns=[], rows=list(rows), explanation=[], row_count=len(rows), elapsed_ms=0
    )


def form(**fields: Any) -> StructuredRequest:
    return StructuredRequest.model_validate(fields)


@pytest.mark.parametrize(
    ("value", "unit", "shown"),
    [
        (96478, "count", "96,478"),
        (Decimal("5067633.16"), "BRL", "R$ 5,067,633.16"),
        (Decimal("0.0677"), "ratio", "6.77%"),
        (Decimal("12.4968"), "days", "12.5 days"),
        (Decimal("4.0864"), "score", "4.09"),
    ],
)
def test_each_unit_has_one_format(value: object, unit: Any, shown: str) -> None:
    assert format_number(value, unit) == shown


def test_single_number(layer: SemanticLayer) -> None:
    facts = build_facts(result((Decimal("13221498.11"),)), form(metric="revenue"), layer, 20)
    assert facts.rows == [["R$ 13,221,498.11"]]
    assert facts.template_answer == "Revenue: R$ 13,221,498.11."
    assert facts.total is None  # nothing to add up
    assert facts.result_text() == "Result (1 row):\nRevenue\nR$ 13,221,498.11"


def test_breakdown_with_names_total_and_template(layer: SemanticLayer) -> None:
    rows = result(("SP", Decimal("500.00")), ("RJ", Decimal("300.50")), ("MG", Decimal("200")))
    facts = build_facts(rows, form(metric="revenue", dimensions=["customer_state"]), layer, 20)
    assert facts.headers == ["Customer state", "Revenue"]
    assert facts.rows[0] == ["SP (São Paulo)", "R$ 500.00"]
    assert facts.total == "R$ 1,000.50"  # a sum metric over a complete breakdown
    assert facts.template_answer == (
        "Revenue by customer state (3 rows): SP (São Paulo): R$ 500.00; "
        "RJ (Rio de Janeiro): R$ 300.50; MG (Minas Gerais): R$ 200.00. Total: R$ 1,000.50."
    )


def test_only_the_top_rows_go_to_the_llm(layer: SemanticLayer) -> None:
    rows = result(*[(f"S{i}", Decimal(100 - i)) for i in range(27)])
    facts = build_facts(rows, form(metric="revenue", dimensions=["customer_state"]), layer, 20)
    assert len(facts.rows) == 20 and facts.total_rows == 27
    assert facts.result_text().startswith("Result (top 20 of 27 rows):")
    assert "(top 5 of 27)" in facts.template_answer
    assert facts.total == format_number(sum(100 - i for i in range(27)), "BRL")  # all 27 rows


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"metric": "late_delivery_rate", "dimensions": ["month"]}, "a rate can't be added"),
        ({"metric": "orders", "dimensions": ["product_category"]}, "count distinct"),
        ({"metric": "revenue", "dimensions": ["customer_state"], "limit": 2}, "only part"),
    ],
)
def test_no_total_where_adding_is_wrong(
    layer: SemanticLayer, fields: dict[str, Any], reason: str
) -> None:
    rows = result(("a", Decimal("0.5")), ("b", Decimal("0.25")))
    assert build_facts(rows, form(**fields), layer, 20).total is None, reason


def test_month_and_year_values(layer: SemanticLayer) -> None:
    by_month = build_facts(
        result((datetime(2017, 3, 1), Decimal("0.141"))),
        form(metric="late_delivery_rate", dimensions=["month"]),
        layer,
        20,
    )
    assert by_month.rows == [["2017-03", "14.10%"]]
    by_year = build_facts(
        result((Decimal("2017"), 43000)), form(metric="orders", dimensions=["year"]), layer, 20
    )
    assert by_year.rows == [["2017", "43,000"]]


def test_no_rows(layer: SemanticLayer) -> None:
    facts = build_facts(result(), form(metric="revenue", dimensions=["customer_state"]), layer, 20)
    assert facts.template_answer == "No data matched the question."
    assert facts.result_text() == "Result: no rows."


def test_allowed_numbers_hold_every_shown_number(layer: SemanticLayer) -> None:
    rows = result(*[(f"S{i}", Decimal(10 + i)) for i in range(25)])
    facts = build_facts(rows, form(metric="revenue", dimensions=["customer_state"]), layer, 20)
    allowed = facts.allowed_numbers
    assert all(cell in allowed for row in facts.rows for cell in row)
    assert "25" in allowed and "20" in allowed  # "top 20 of 25" may be quoted
    assert facts.total in allowed
