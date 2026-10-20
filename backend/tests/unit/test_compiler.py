from datetime import date
from typing import Any

import pytest

from adaa.semantic_layer.compiler import CompiledQuery, CompileError, compile_request
from adaa.semantic_layer.definitions import SemanticLayer, load
from adaa.semantic_layer.request import StructuredRequest


@pytest.fixture(scope="module")
def layer() -> SemanticLayer:
    return load()


def compile_form(layer: SemanticLayer, **fields: Any) -> CompiledQuery:
    return compile_request(StructuredRequest.model_validate(fields), layer)


def test_revenue_by_state(layer: SemanticLayer) -> None:
    q = compile_form(
        layer,
        metric="revenue",
        dimensions=["customer_state"],
        period={"start": "2017-01-01", "end": "2017-12-31"},
        limit=10,
    )
    assert "sum(order_items.price) AS revenue" in q.sql
    assert "JOIN orders ON order_items.order_id = orders.order_id" in q.sql
    assert "JOIN customers ON orders.customer_id = customers.customer_id" in q.sql
    assert "orders.order_status = 'delivered'" in q.sql  # the metric's own filter (D2)
    assert "GROUP BY customers.customer_state" in q.sql
    assert "ORDER BY revenue DESC" in q.sql  # breakdown with no sort: highest first
    assert q.params["period_start"] == date(2017, 1, 1)
    assert q.params["period_end"] == date(2018, 1, 1)  # end day included
    assert q.params["row_limit"] == 10
    assert q.columns == ["customer_state", "revenue"]


def test_only_the_joins_that_are_needed(layer: SemanticLayer) -> None:
    q = compile_form(layer, metric="review_count")
    assert "FROM reviews" in q.sql
    assert "JOIN" not in q.sql and "WHERE" not in q.sql  # one table, no filter: no join

    with_period = compile_form(
        layer, metric="review_count", period={"start": "2018-01-01", "end": "2018-01-31"}
    )
    assert "JOIN orders" in with_period.sql  # the period is on the order date
    assert "customers" not in with_period.sql and "order_items" not in with_period.sql


def test_category_uses_a_left_join(layer: SemanticLayer) -> None:
    q = compile_form(layer, metric="revenue", dimensions=["product_category"])
    assert "JOIN products ON" in q.sql
    assert "LEFT JOIN category_translation ON" in q.sql


def test_defaults_when_the_form_is_short(layer: SemanticLayer) -> None:
    q = compile_form(layer, metric="revenue")
    assert "period_start" not in q.params  # no period asked for → all available data
    assert "order_purchase_timestamp" not in q.sql
    assert q.params["row_limit"] == 1000
    assert "GROUP BY" not in q.sql and "ORDER BY" not in q.sql
    assert "Period: all available data (no period was asked for)." in q.explanation


def test_filters_become_placeholders(layer: SemanticLayer) -> None:
    q = compile_form(
        layer,
        metric="revenue",
        filters=[{"dimension": "customer_state", "op": "in", "values": ["SP", "RJ"]}],
    )
    assert "customers.customer_state IN (%(f0_0)s, %(f0_1)s)" in q.sql
    assert q.params["f0_0"] == "SP" and q.params["f0_1"] == "RJ"


def test_injection_attempt_stays_a_value(layer: SemanticLayer) -> None:
    attack = "SP'; DROP TABLE orders; --"
    q = compile_form(
        layer,
        metric="revenue",
        filters=[{"dimension": "customer_state", "op": "=", "values": [attack]}],
    )
    assert "DROP TABLE" not in q.sql
    assert q.params["f0_0"] == attack


def test_explanation_lines(layer: SemanticLayer) -> None:
    q = compile_form(
        layer,
        metric="revenue",
        dimensions=["customer_state"],
        filters=[{"dimension": "product_category", "op": "=", "values": ["toys"]}],
        limit=5,
    )
    text = "\n".join(q.explanation)
    assert "Revenue = item price, excluding freight" in text
    assert "Broken down by: Customer state." in text
    assert "Filter: Product category = toys." in text
    assert "Showing at most 5 rows." in text
    assert f"v{layer.version}" in text


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"metric": "profit"}, "No metric called 'profit'"),
        ({"metric": "revenue", "dimensions": ["country"]}, "No dimension called 'country'"),
        ({"metric": "total_paid", "dimensions": ["product_category"]}, "counted twice"),
        ({"metric": "revenue", "dimensions": ["payment_type"]}, "counted twice"),
        (
            {
                "metric": "average_review_score",
                "filters": [{"dimension": "seller", "op": "=", "values": ["s1"]}],
            },
            "counted twice",
        ),
        (
            {"metric": "revenue", "dimensions": ["month"], "sort": {"by": "freight"}},
            "Can't sort by 'freight'",
        ),
    ],
)
def test_refusals(layer: SemanticLayer, fields: dict[str, Any], message: str) -> None:
    with pytest.raises(CompileError, match=message):
        compile_form(layer, **fields)
