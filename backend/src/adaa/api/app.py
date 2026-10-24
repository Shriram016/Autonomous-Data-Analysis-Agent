"""The API: the "waiter" between the UI and the workers (§0 M1.5).

    POST /questions               take a question, queue it, return its id at once
    GET  /questions/{id}          the question's row: state, answer, cost, times
    GET  /questions/{id}/events   the live progress, as Server-Sent Events (SSE)
    GET  /health                  are Postgres and Redis answering?

The API never runs the agent: workers do, and the API only talks to Postgres (rows) and
Redis (the queue and the progress streams). Run locally from backend/:
    uv run uvicorn adaa.api.app:app --reload
"""

import json
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from adaa.conversation.questions import LOCAL_OWNER, QuestionRecord
from adaa.settings import get_settings
from adaa.worker import events, jobs

MAX_QUESTION_CHARS = 500  # §0: a real question is 1-2 sentences; caps cost and abuse
KEEP_ALIVE_S = 15  # send a "still here" line when quiet, so proxies keep the stream open
STREAM_LIMIT_S = 180  # longer than the worker's hard time limit (180 s) plus queue time

app = FastAPI(title="ADAA API", version="0.1.0")


class QuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class QuestionCreated(BaseModel):
    id: UUID


def current_owner() -> str:
    """Who is asking. The one place that changes in M6: Keycloak's token instead of this."""
    return LOCAL_OWNER


def owned_question(question_id: UUID, owner: str) -> QuestionRecord:
    record = jobs.get_result(question_id, owner)
    if record is None:  # unknown OR someone else's: the same answer, so nothing leaks
        raise HTTPException(status_code=404, detail="No such question.")
    return record


@app.post("/questions", status_code=202)
def ask_question(body: QuestionIn, owner: str = Depends(current_owner)) -> QuestionCreated:
    """202 Accepted: the question is queued, not answered yet."""
    return QuestionCreated(id=jobs.submit(owner, body.question))


@app.get("/questions/{question_id}")
def read_question(question_id: UUID, owner: str = Depends(current_owner)) -> QuestionRecord:
    return owned_question(question_id, owner)


def sse(event: str, data: dict[str, Any], event_id: str | None = None) -> str:
    """One Server-Sent Event: optional id line, event name, JSON data, blank line."""
    head = f"id: {event_id}\n" if event_id else ""
    return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n"


def final_event(record: QuestionRecord, event_id: str | None = None) -> str:
    answer = record.answer.model_dump(mode="json") if record.answer else None
    return sse(record.state, {"state": record.state, "answer": answer}, event_id)


def event_stream(question_id: UUID, owner: str, after_id: str) -> Iterator[str]:
    record = owned_question(question_id, owner)
    if record.state in ("done", "failed") and after_id == "0":
        yield final_event(record)  # already finished (e.g. a page reload): answer at once
        return
    deadline = time.monotonic() + STREAM_LIMIT_S
    while time.monotonic() < deadline:
        batch = events.read(question_id, after_id, wait_ms=KEEP_ALIVE_S * 1000)
        if not batch:
            yield ": still here\n\n"  # a comment line: browsers ignore it, proxies see traffic
            continue
        for event_id, event in batch:
            after_id = event_id
            if event.kind in ("done", "failed"):  # the last event: send the stored answer
                yield final_event(owned_question(question_id, owner), event_id)
                return
            yield sse("step", {"text": event.text}, event_id)
    yield sse("timeout", {"text": "No answer yet. Reload the page to check again."})


@app.get("/questions/{question_id}/events")
def stream_question(
    question_id: UUID,
    owner: str = Depends(current_owner),
    last_event_id: str | None = Header(default=None),  # sent by the browser on reconnect
) -> StreamingResponse:
    owned_question(question_id, owner)  # 404 before the stream starts
    return StreamingResponse(
        event_stream(question_id, owner, last_event_id or "0"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # don't buffer it
    )


def check_postgres() -> bool:
    try:
        with psycopg.connect(get_settings().postgres_conninfo("app")) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


def check_redis() -> bool:
    try:
        return bool(events.connect().ping())
    except Exception:  # any Redis or network error means "not answering"
        return False


@app.get("/health")
def health() -> JSONResponse:
    status = {"postgres": check_postgres(), "redis": check_redis()}
    code = 200 if all(status.values()) else 503
    return JSONResponse({name: "ok" if ok else "down" for name, ok in status.items()}, code)
