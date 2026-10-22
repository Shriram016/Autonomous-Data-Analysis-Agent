from datetime import date, datetime

import pytest

from adaa.agent.notes import NoDataError, data_note, find_data_date
from adaa.semantic_layer.definitions import load
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult


def months(*counts: tuple[datetime, int]) -> QueryResult:
    rows: list[tuple[object, ...]] = list(counts)
    return QueryResult(columns=[], rows=rows, explanation=[], row_count=len(rows), elapsed_ms=0)


def test_data_date_is_the_end_of_the_last_full_month() -> None:
    asked: list[StructuredRequest] = []

    def fake_ask(form: StructuredRequest) -> QueryResult:
        asked.append(form)
        return months(
            (datetime(2018, 7, 1), 6000),
            (datetime(2018, 8, 1), 6300),
            (datetime(2018, 9, 1), 16),  # thin: the data is ending
            (datetime(2016, 9, 1), 4),
        )

    assert find_data_date(load(), fake_ask) == date(2018, 8, 31)
    assert asked == [StructuredRequest(metric="orders", dimensions=["month"])]


def test_february_ends_on_the_right_day() -> None:
    assert find_data_date(load(), lambda _: months((datetime(2018, 2, 1), 500))) == date(
        2018, 2, 28
    )


def test_no_full_month_is_a_clear_error() -> None:
    with pytest.raises(NoDataError, match="No month has 500 or more orders"):
        find_data_date(load(), lambda _: months((datetime(2018, 9, 1), 16)))


def test_note_text() -> None:
    assert data_note(date(2018, 8, 31)) == "Data as of 2018-08-31."
