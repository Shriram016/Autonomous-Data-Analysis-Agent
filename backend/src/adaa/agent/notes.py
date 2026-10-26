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

from adaa.agent.facts import period_label
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


def find_data_span(ask: Callable[[StructuredRequest], QueryResult]) -> tuple[date, date]:
    """The first and the last month with any order, thin ones included (metadata replies)."""
    result = ask(StructuredRequest(metric="orders", dimensions=["month"]))
    months = [month for month, _ in result.rows if isinstance(month, datetime | date)]
    if not months:
        raise NoDataError("No month has any orders.")
    first, last = min(months), max(months)
    return date(first.year, first.month, 1), date(last.year, last.month, 1)


def data_note(data_date: date) -> str:
    return f"Data as of {data_date.isoformat()}."


def partial_period_note(form: StructuredRequest, data_date: date) -> str | None:
    """A sentence for the answer when an asked period runs past the data date (2026-10-26):
    "revenue in 2018" covers January–August only. The numbers are not changed."""
    late = [p for p in (form.period, form.compare_to) if p and p.end > data_date]
    if not late:
        return None
    return (
        f"Data is complete only until {data_date.isoformat()}, "
        f"so {period_label(late[0])} is not a full period."
    )
