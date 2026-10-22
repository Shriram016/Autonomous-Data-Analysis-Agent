"""The data date: how recent the data is (§0 M1.3, "today" rule and step 5 notes).

The data date is the last day of the last month with enough orders (the semantic layer's
thin_month rule, 500). It is the agent's "today" for relative dates ("last month"), and every
answer shows it as one code-made line: "Data as of 2018-08-31". Later months with only a few
orders (the data stops in October 2018) don't count as "today".

Read once at agent start through the normal compiler and runner, like the value catalogue.
"""

import calendar
from collections.abc import Callable
from datetime import date, datetime

from adaa.semantic_layer.definitions import SemanticLayer
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult


class NoDataError(Exception):
    """No month has enough orders to set a data date."""


def find_data_date(layer: SemanticLayer, ask: Callable[[StructuredRequest], QueryResult]) -> date:
    minimum = int(layer.defaults["thin_month"].means)
    result = ask(StructuredRequest(metric="orders", dimensions=["month"]))
    full_months = [
        month
        for month, orders in result.rows
        if isinstance(month, datetime | date) and int(str(orders)) >= minimum
    ]
    if not full_months:
        raise NoDataError(f"No month has {minimum} or more orders.")
    last = max(full_months)
    return date(last.year, last.month, calendar.monthrange(last.year, last.month)[1])


def data_note(data_date: date) -> str:
    return f"Data as of {data_date.isoformat()}."
