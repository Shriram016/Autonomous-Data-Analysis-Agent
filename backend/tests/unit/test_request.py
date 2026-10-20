from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from adaa.semantic_layer.request import StructuredRequest


def make(**fields: Any) -> StructuredRequest:
    return StructuredRequest.model_validate({"metric": "revenue", **fields})


def test_smallest_valid_form() -> None:
    request = make()
    assert request.metric == "revenue"
    assert request.dimensions == [] and request.filters == []
    assert request.period is None and request.limit is None


def test_full_valid_form() -> None:
    request = make(
        dimensions=["customer_state"],
        filters=[{"dimension": "product_category", "op": "in", "values": ["toys", "books"]}],
        period={"start": "2017-01-01", "end": "2017-12-31"},
        sort={"by": "revenue", "direction": "desc"},
        limit=10,
    )
    assert request.period is not None and request.period.start == date(2017, 1, 1)
    assert request.filters[0].values == ["toys", "books"]
    assert request.sort is not None and request.sort.direction == "desc"


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"metric": ""}, "metric"),
        ({"dimensions": ["month", "customer_state", "product_category"]}, "dimensions"),
        ({"dimensions": ["month", "month"]}, "repeated"),
        ({"limit": 0}, "limit"),
        ({"limit": 1001}, "limit"),
        ({"period": {"start": "2018-01-01", "end": "2017-01-01"}}, "after end"),
        ({"filters": [{"dimension": "seller", "op": "like", "values": ["x"]}]}, "op"),
        ({"filters": [{"dimension": "seller", "op": "in", "values": []}]}, "values"),
        ({"filters": [{"dimension": "seller", "op": "=", "values": ["a", "b"]}]}, "exactly one"),
        ({"sort": {"by": "revenue", "direction": "up"}}, "direction"),
        ({"sql": "DROP TABLE orders"}, "sql"),  # unknown fields are refused
    ],
)
def test_broken_forms_are_refused(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        make(**fields)


def test_form_has_a_json_schema_for_the_llm() -> None:
    schema = StructuredRequest.model_json_schema()
    assert schema["required"] == ["metric"]
    assert schema["additionalProperties"] is False
