"""Progress events: what a worker is doing on one question, for the SSE stream (§0 M1.5).

One Redis Stream per question, `adaa:events:<question id>`, separate from Celery's job queue:
the queue holds one slip per waiting question; a stream holds the steps of one question.
The worker publishes ("Understanding the question…", …, "done"); the API reads them and
sends them to the UI. Every message gets an id in order, so a UI that reconnects sends its
last id (Last-Event-ID) and continues where it stopped. A stream expires after 1 day.
"""

from typing import Any, Literal
from uuid import UUID

import redis
from pydantic import BaseModel, ConfigDict

from adaa.settings import get_settings

STREAM_TTL_S = 24 * 60 * 60  # same as the job results
MAX_EVENTS = 100  # a question sends about 5; this only guards against a runaway loop

EventKind = Literal["step", "done", "failed"]


class ProgressEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: EventKind  # step: work in progress; done / failed: the last event of a question
    text: str = ""  # shown to the user, e.g. "Running the query…"


def stream_key(question_id: UUID) -> str:
    return f"adaa:events:{question_id}"


def connect() -> redis.Redis:
    return redis.Redis.from_url(
        get_settings().redis_url, decode_responses=True, socket_connect_timeout=2
    )


def publish(question_id: UUID, event: ProgressEvent, r: redis.Redis | None = None) -> str:
    """Add one event; return its stream id."""
    r = r or connect()
    key = stream_key(question_id)
    event_id = r.xadd(key, {"event": event.model_dump_json()}, maxlen=MAX_EVENTS)
    r.expire(key, STREAM_TTL_S)
    return str(event_id)


def read(
    question_id: UUID,
    after_id: str = "0",
    wait_ms: int | None = None,
    r: redis.Redis | None = None,
) -> list[tuple[str, ProgressEvent]]:
    """Every event after `after_id` ("0" = from the start), in order.

    wait_ms: if there is no new event yet, wait up to this long for one (None = don't wait).
    Never pass 0: in Redis that means "wait for ever".
    """
    r = r or connect()
    # redis-py types this reply very widely; its real shape is [[key, [(id, {field: value})]]]
    reply: Any = r.xread({stream_key(question_id): after_id}, block=wait_ms)
    if not reply:
        return []
    _, messages = reply[0]
    return [
        (event_id, ProgressEvent.model_validate_json(data["event"])) for event_id, data in messages
    ]
