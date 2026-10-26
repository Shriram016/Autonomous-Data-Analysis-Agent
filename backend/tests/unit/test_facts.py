from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from adaa.agent.facts import (
    MAX_BARS,
    build_chart,
    build_facts,
    format_change,
    format_change_pct,
    format_number,
    period_label,
)
from adaa.semantic_layer.definitions import SemanticLayer, load
from adaa.semantic_layer.request import Period, StructuredRequest
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


# --- the chart (M1.6) ---


def test_a_single_number_gets_no_chart(layer: SemanticLayer) -> None:
    assert build_chart(result((Decimal(5),)), form(metric="revenue"), layer) is None


def test_a_time_breakdown_gets_a_line_with_every_point_oldest_first(layer: SemanticLayer) -> None:
    rows = result(
        (datetime(2017, 3, 1), Decimal("0.0456")), (datetime(2017, 1, 1), Decimal("0.0293"))
    )
    chart = build_chart(rows, form(metric="late_delivery_rate", dimensions=["month"]), layer)
    assert chart is not None and chart.kind == "line" and chart.unit == "ratio"
    assert [(p.x, p.y) for p in chart.points] == [("2017-01", 0.0293), ("2017-03", 0.0456)]
    assert (chart.x_label, chart.y_label) == ("Month", "Late-delivery rate")


def test_a_category_breakdown_gets_at_most_20_bars_with_raw_numbers(layer: SemanticLayer) -> None:
    rows = result(
        *[("SP", Decimal("2136258.96"))] + [(f"S{i}", Decimal(100 - i)) for i in range(26)]
    )
    chart = build_chart(rows, form(metric="revenue", dimensions=["customer_state"]), layer)
    assert chart is not None and chart.kind == "bar" and chart.unit == "BRL"
    assert len(chart.points) == MAX_BARS
    assert chart.points[0].x == "SP (São Paulo)" and chart.points[0].y == 2136258.96  # raw


def test_two_breakdowns_get_no_chart_for_now(layer: SemanticLayer) -> None:
    rows = result((datetime(2017, 1, 1), "SP", Decimal(1)))
    two = form(metric="revenue", dimensions=["month", "customer_state"])
    assert build_chart(rows, two, layer) is None


# --- period comparison (M2 step 1, slice C) ---

Y2018 = {"start": "2018-01-01", "end": "2018-12-31"}
Y2017 = {"start": "2017-01-01", "end": "2017-12-31"}


@pytest.mark.parametrize(
    ("period", "label"),
    [
        (Y2018, "2018"),
        ({"start": "2018-03-01", "end": "2018-03-31"}, "2018-03"),
        ({"start": "2018-01-01", "end": "2018-06-30"}, "2018-01-01 to 2018-06-30"),
    ],
)
def test_period_labels(period: dict[str, str], label: str) -> None:
    assert period_label(Period.model_validate(period)) == label


def test_signed_changes() -> None:
    assert format_change(Decimal("800"), "BRL") == "+R$ 800.00"
    assert format_change(Decimal("-15"), "count") == "-15"
    assert format_change(Decimal("0.013"), "ratio") == "+1.30 points"
    assert format_change(None, "BRL") == "no value"
    assert format_change_pct(Decimal("0.381")) == "+38.1%"
    assert format_change_pct(None) == "n/a"


def test_comparison_table_and_template(layer: SemanticLayer) -> None:
    request = form(metric="revenue", dimensions=["customer_state"], period=Y2018, compare_to=Y2017)
    rows = result(
        ("SP", Decimal(150), Decimal(100), Decimal(50), Decimal("0.5")),
        ("AC", Decimal(5), None, None, None),
    )
    facts = build_facts(rows, request, layer, max_rows=20)
    assert facts.headers == ["Customer state", "Revenue 2018", "Revenue 2017", "Change", "Change %"]
    assert facts.rows[0] == ["SP (São Paulo)", "R$ 150.00", "R$ 100.00", "+R$ 50.00", "+50.0%"]
    assert facts.rows[1] == ["AC (Acre)", "R$ 5.00", "no value", "no value", "n/a"]
    assert facts.total is None  # no single column to add up
    assert facts.template_answer == (
        "Revenue, 2018 vs 2017: SP (São Paulo): R$ 150.00 vs R$ 100.00 (+R$ 50.00, +50.0%); "
        "AC (Acre): R$ 5.00 vs no value (no value, n/a)."
    )
    assert build_chart(rows, request, layer) is None  # table only for now


def test_a_rate_comparison_has_no_change_pct(layer: SemanticLayer) -> None:
    request = form(metric="late_delivery_rate", period=Y2018, compare_to=Y2017)
    facts = build_facts(
        result((Decimal("0.081"), Decimal("0.068"), Decimal("0.013"))), request, layer, 20
    )
    assert facts.headers == ["Late-delivery rate 2018", "Late-delivery rate 2017", "Change"]
    assert facts.template_answer == (
        "Late-delivery rate, 2018 vs 2017: 8.10% vs 6.80% (+1.30 points)."
    )


# --- support counts for rates (slice D) ---


def test_rate_counts_go_to_the_llm_and_the_template(layer: SemanticLayer) -> None:
    rows = QueryResult(
        columns=["cancellation_rate"],
        rows=[(Decimal("0.00628513"),)],
        explanation=[],
        row_count=1,
        elapsed_ms=0,
        support=[(625, 99441)],
    )
    facts = build_facts(rows, form(metric="cancellation_rate"), layer, max_rows=20)
    assert facts.support == ["625 of 99,441 orders canceled"]
    assert "0.63% (625 of 99,441 orders canceled)" in facts.result_text()
    assert facts.template_answer == "Cancellation rate: 0.63% (625 of 99,441 orders canceled)."
    assert "625 of 99,441 orders canceled" in facts.allowed_numbers
    assert facts.rows == [["0.63%"]]  # the table is unchanged


def test_an_average_shows_how_many_rows_it_is_based_on(layer: SemanticLayer) -> None:
    rows = QueryResult(
        columns=["average_review_score"],
        rows=[(Decimal("4.0864"),)],
        explanation=[],
        row_count=1,
        elapsed_ms=0,
        support=[(None, 99224)],
    )
    facts = build_facts(rows, form(metric="average_review_score"), layer, max_rows=20)
    assert facts.template_answer == "Average review score: 4.09 (based on 99,224 reviews)."
