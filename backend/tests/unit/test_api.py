"""The API with FastAPI's test client; the table, the queue and the streams are fakes."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from adaa.agent.state import NO_USAGE, FinishedAnswer, Versions
from adaa.api import app as api
from adaa.conversation.questions import LOCAL_OWNER, QuestionRecord, QuestionState
from adaa.worker.events import ProgressEvent

QID = uuid4()
ANSWER = FinishedAnswer(
    question="Total revenue",
    status="answered",
    text="Revenue was R$ 13,221,498.11.",
    versions=Versions(
        semantic_layer="0.3.3 (x)", agent_prompt="0.1.0 (y)", answer_prompt="0.1.0 (z)"
    ),
    usage=NO_USAGE,
)


def record(state: QuestionState, answer: FinishedAnswer | None = None) -> QuestionRecord:
    now = datetime.now(UTC)
    return QuestionRecord(
        id=QID,
        owner=LOCAL_OWNER,
        question="Total revenue",
        state=state,
        answer=answer,
        input_tokens=0,
        output_tokens=0,
        thinking_tokens=0,
        cost_usd=Decimal(0),
        created_at=now,
        started_at=None,
        finished_at=None,
        wait_seconds=None,
        total_seconds=None,
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(api.app)


def rows(monkeypatch: pytest.MonkeyPatch, *states: QuestionRecord | None) -> None:
    """get_result returns these, one per call (the last one repeats)."""
    queue = list(states)

    def get_result(question_id: UUID, owner: str) -> QuestionRecord | None:
        if owner != LOCAL_OWNER:
            return None
        return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(api.jobs, "get_result", get_result)


def test_submit_returns_an_id_at_once(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []

    def submit(owner: str, question: str) -> UUID:
        sent.append((owner, question))
        return QID

    monkeypatch.setattr(api.jobs, "submit", submit)
    reply = client.post("/questions", json={"question": "  Total revenue  "})
    assert reply.status_code == 202 and reply.json() == {"id": str(QID)}
    assert sent == [(LOCAL_OWNER, "Total revenue")]  # spaces stripped, owner from current_owner


@pytest.mark.parametrize("question", ["", "   ", "x" * 501])
def test_empty_or_too_long_questions_are_refused(client: TestClient, question: str) -> None:
    assert client.post("/questions", json={"question": question}).status_code == 422


def test_a_500_character_question_is_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api.jobs, "submit", lambda owner, q: QID)
    assert client.post("/questions", json={"question": "x" * 500}).status_code == 202


def test_get_returns_the_row(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    rows(monkeypatch, record("done", ANSWER))
    body = client.get(f"/questions/{QID}").json()
    assert body["state"] == "done" and body["answer"]["text"] == ANSWER.text


def test_unknown_or_not_yours_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    rows(monkeypatch, None)
    assert client.get(f"/questions/{QID}").status_code == 404
    assert client.get(f"/questions/{QID}/events").status_code == 404


def parse(stream: str) -> list[dict[str, str]]:
    """Split an SSE body into events: {"id": ..., "event": ..., "data": ...}."""
    out = []
    for block in stream.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.splitlines() if not line.startswith(":")
        )
        if fields:
            out.append(fields)
    return out


def fake_events(
    monkeypatch: pytest.MonkeyPatch, batches: list[list[tuple[str, ProgressEvent]]]
) -> list[str]:
    asked_after: list[str] = []

    def read(
        question_id: UUID, after_id: str, wait_ms: int | None = None
    ) -> list[tuple[str, ProgressEvent]]:
        asked_after.append(after_id)
        return batches.pop(0) if batches else []

    monkeypatch.setattr(api.events, "read", read)
    return asked_after


def test_stream_sends_the_steps_then_the_answer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows(monkeypatch, record("running"), record("running"), record("done", ANSWER))
    fake_events(
        monkeypatch,
        [
            [("1-0", ProgressEvent(kind="step", text="Understanding the question…"))],
            [],  # a quiet moment: the stream sends a keep-alive line
            [
                ("2-0", ProgressEvent(kind="step", text="Running the query…")),
                ("3-0", ProgressEvent(kind="done")),
            ],
        ],
    )
    body = client.get(f"/questions/{QID}/events").text
    assert ": still here" in body
    got = parse(body)
    assert [(e["id"], e["event"]) for e in got] == [
        ("1-0", "step"),
        ("2-0", "step"),
        ("3-0", "done"),
    ]
    assert '"Running the query…"' in got[1]["data"] or "Running the query" in got[1]["data"]
    assert ANSWER.text in got[2]["data"]  # the stored answer comes with the last event


def test_a_reconnect_continues_after_last_event_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows(monkeypatch, record("running"), record("running"), record("done", ANSWER))
    asked_after = fake_events(monkeypatch, [[("3-0", ProgressEvent(kind="done"))]])
    client.get(f"/questions/{QID}/events", headers={"Last-Event-ID": "2-0"})
    assert asked_after[0] == "2-0"


def test_a_finished_question_answers_at_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows(monkeypatch, record("done", ANSWER))
    asked_after = fake_events(monkeypatch, [])
    got = parse(client.get(f"/questions/{QID}/events").text)
    assert [e["event"] for e in got] == ["done"] and asked_after == []  # no wait on the stream


@pytest.mark.parametrize(("postgres", "redis", "code"), [(True, True, 200), (True, False, 503)])
def test_health(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, postgres: bool, redis: bool, code: int
) -> None:
    monkeypatch.setattr(api, "check_postgres", lambda: postgres)
    monkeypatch.setattr(api, "check_redis", lambda: redis)
    reply = client.get("/health")
    assert reply.status_code == code
    assert reply.json() == {"postgres": "ok", "redis": "ok" if redis else "down"}
