"""The whole numbers path on real data: form → compiler → runner (adaa_query) → Postgres.

Needs: docker compose up, data loaded (load_olist), roles created (adaa.db.roles).
"""

from decimal import Decimal
from typing import Any

import pytest

from adaa.semantic_layer import runner
from adaa.semantic_layer.compiler import CompiledQuery
from adaa.semantic_layer.definitions import SemanticLayer, load
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import (
    DataUnavailableError,
    QueryResult,
    QueryTimeoutError,
    answer_request,
    run_query,
)
from adaa.settings import get_settings

pytestmark = pytest.mark.integration

ALL_DATES = {"start": "2016-09-01", "end": "2018-10-31"}  # every order in the data
YEAR_2017 = {"start": "2017-01-01", "end": "2017-12-31"}


@pytest.fixture(scope="module")
def layer() -> SemanticLayer:
    return load()


def ask(layer: SemanticLayer, **fields: Any) -> QueryResult:
    return answer_request(StructuredRequest.model_validate(fields), layer)


def single_value(result: QueryResult) -> Any:
    assert result.row_count == 1
    return result.rows[0][-1]


def by_key(result: QueryResult) -> dict[str, Decimal]:
    """Rows of (dimension, metric) as {dimension: metric}."""
    return {str(row[0]): Decimal(str(row[1])) for row in result.rows}


def test_no_period_means_all_data(layer: SemanticLayer) -> None:
    for metric in ("revenue", "orders", "customers", "review_count"):
        no_period = single_value(ask(layer, metric=metric))
        full_range = single_value(ask(layer, metric=metric, period=ALL_DATES))
        assert no_period == full_range, metric


def test_known_totals_match_the_m06_check(layer: SemanticLayer) -> None:
    revenue = single_value(ask(layer, metric="revenue", period=ALL_DATES))
    late = single_value(ask(layer, metric="late_delivery_rate", period=ALL_DATES))
    customers = single_value(ask(layer, metric="customers", period=ALL_DATES))
    assert revenue == Decimal("13221498.11")
    assert round(float(late), 4) == 0.0677
    assert customers == 93358


def test_breakdown_adds_up_to_the_total(layer: SemanticLayer) -> None:
    by_state = ask(layer, metric="revenue", dimensions=["customer_state"], period=YEAR_2017)
    total = single_value(ask(layer, metric="revenue", period=YEAR_2017))
    assert by_state.row_count == 27  # every Brazilian state appears in 2017
    assert sum(by_key(by_state).values()) == total


def test_filter_agrees_with_the_breakdown(layer: SemanticLayer) -> None:
    by_state = ask(layer, metric="revenue", dimensions=["customer_state"], period=YEAR_2017)
    sp_row = by_key(by_state)["SP"]
    sp_only = ask(
        layer,
        metric="revenue",
        period=YEAR_2017,
        filters=[{"dimension": "customer_state", "op": "=", "values": ["SP"]}],
    )
    assert single_value(sp_only) == sp_row


def test_limit_and_sort(layer: SemanticLayer) -> None:
    top3 = ask(layer, metric="revenue", dimensions=["customer_state"], period=YEAR_2017, limit=3)
    values = list(by_key(top3).values())
    assert top3.row_count == 3
    assert values == sorted(values, reverse=True)
    assert top3.columns == ["customer_state", "revenue"]


def test_metric_from_another_table(layer: SemanticLayer) -> None:
    reviews = single_value(ask(layer, metric="review_count", period=ALL_DATES))
    assert reviews == 99224  # every review row; its order date is inside the full range


def test_slow_query_gives_the_timeout_message() -> None:
    slow = CompiledQuery(sql="SELECT pg_sleep(6)", params={}, columns=["x"], explanation=[])
    with pytest.raises(QueryTimeoutError, match="took too long"):
        run_query(slow, get_settings().postgres_conninfo("query"))


def test_unreachable_database_gives_the_unavailable_message() -> None:
    nowhere = get_settings().model_copy(update={"db_port": 1}).postgres_conninfo("query")
    probe = CompiledQuery(sql="SELECT 1", params={}, columns=["x"], explanation=[])
    with pytest.raises(DataUnavailableError, match="temporarily unavailable"):
        run_query(probe, nowhere)


def test_answer_request_always_logs_in_as_adaa_query(
    layer: SemanticLayer, monkeypatch: pytest.MonkeyPatch
) -> None:
    used: list[str] = []
    real_run_query = runner.run_query

    def spy(compiled: CompiledQuery, conninfo: str) -> QueryResult:
        used.append(conninfo)
        return real_run_query(compiled, conninfo)

    monkeypatch.setattr(runner, "run_query", spy)
    ask(layer, metric="orders")
    assert len(used) == 1 and "user=adaa_query " in used[0]


def test_new_v040_metrics_on_real_data(layer: SemanticLayer) -> None:
    """Values from data-profile.md: 625 of 99,441 orders canceled (F3); 112,650 items."""
    rate = single_value(ask(layer, metric="cancellation_rate"))
    assert round(float(rate), 6) == round(625 / 99441, 6)
    by_status = by_key(ask(layer, metric="items_sold", dimensions=["order_status"]))
    assert sum(by_status.values()) == 112650  # every item, in every status


def test_repeat_customer_rate_on_real_data(layer: SemanticLayer) -> None:
    """Data profile F4: about 3% of people ordered more than once."""
    overall = float(single_value(ask(layer, metric="repeat_customer_rate")))
    assert 0.025 < overall < 0.035
    by_month = by_key(ask(layer, metric="repeat_customer_rate", dimensions=["month"]))
    monthly = sorted(by_month.values())
    assert monthly[len(monthly) // 2] < Decimal(overall)  # median month: fewer buy twice


def test_quarters_add_up_to_the_year(layer: SemanticLayer) -> None:
    quarters = ask(layer, metric="revenue", dimensions=["quarter"], period=YEAR_2017)
    assert [row[0] for row in quarters.rows] == ["2017-Q1", "2017-Q2", "2017-Q3", "2017-Q4"]
    assert sum(by_key(quarters).values()) == single_value(
        ask(layer, metric="revenue", period=YEAR_2017)
    )


def test_canceled_orders_are_not_zero(layer: SemanticLayer) -> None:
    """D2 is a default: naming a status replaces it (before v0.3.0 this returned 0)."""
    canceled = ask(
        layer,
        metric="orders",
        filters=[{"dimension": "order_status", "op": "=", "values": ["canceled"]}],
    )
    assert single_value(canceled) == 461  # canceled orders that have items
    by_status = by_key(ask(layer, metric="orders", dimensions=["order_status"]))
    assert by_status["canceled"] == 461 and by_status["delivered"] == 96478
    assert single_value(ask(layer, metric="orders")) == 96478  # no status named → delivered
