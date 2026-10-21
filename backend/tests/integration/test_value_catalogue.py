"""The value catalogue from the real data (needs docker compose up + data loaded)."""

import pytest

from adaa.agent.values import build_catalogue
from adaa.semantic_layer.definitions import load
from adaa.semantic_layer.runner import answer_request

pytestmark = pytest.mark.integration


def test_real_catalogue() -> None:
    layer = load()
    catalogue = build_catalogue(layer, lambda form: answer_request(form, layer))
    values = catalogue.values
    assert "toys" in values["product_category"] and len(values["product_category"]) > 60
    assert len(values["customer_state"]) == 27 and "SP" in values["customer_state"]
    assert values["review_score"] == [1, 2, 3, 4, 5]
    assert "credit_card" in values["payment_type"]
    assert values["order_status"] == ["delivered"]  # the D2 default: only what a query can match
    assert "seller" not in values  # ~3,000 seller IDs: too many to list
