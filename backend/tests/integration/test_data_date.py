"""The data date from the real data (needs docker compose up + data loaded)."""

from datetime import date

import pytest

from adaa.agent.notes import find_data_date
from adaa.semantic_layer.definitions import load
from adaa.semantic_layer.runner import answer_request

pytestmark = pytest.mark.integration


def test_real_data_date() -> None:
    layer = load()
    assert find_data_date(layer, lambda form: answer_request(form, layer)) == date(2018, 8, 31)
