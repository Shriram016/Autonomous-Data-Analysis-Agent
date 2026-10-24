"""Progress events on real Redis (needs docker compose up)."""

import time
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from adaa.worker import events
from adaa.worker.events import ProgressEvent

pytestmark = pytest.mark.integration


@pytest.fixture
def question_id() -> Iterator[UUID]:
    qid = uuid4()
    yield qid
    events.connect().delete(events.stream_key(qid))


STEPS = [
    ProgressEvent(kind="step", text="Understanding the question…"),
    ProgressEvent(kind="step", text="Running the query…"),
    ProgressEvent(kind="done"),
]


def test_events_come_back_in_order(question_id: UUID) -> None:
    ids = [events.publish(question_id, e) for e in STEPS]
    got = events.read(question_id)
    assert [event_id for event_id, _ in got] == ids
    assert [e for _, e in got] == STEPS


def test_a_reconnecting_reader_continues_after_its_last_id(question_id: UUID) -> None:
    ids = [events.publish(question_id, e) for e in STEPS]
    got = events.read(question_id, after_id=ids[1])  # Last-Event-ID = the 2nd event
    assert [e for _, e in got] == [ProgressEvent(kind="done")]


def test_the_stream_expires_after_one_day(question_id: UUID) -> None:
    events.publish(question_id, STEPS[0])
    ttl = events.connect().ttl(events.stream_key(question_id))
    assert 0 < ttl <= events.STREAM_TTL_S


def test_no_event_yet_waits_briefly_then_returns_nothing(question_id: UUID) -> None:
    started = time.monotonic()
    assert events.read(question_id, wait_ms=200) == []
    assert time.monotonic() - started >= 0.15  # it really waited
