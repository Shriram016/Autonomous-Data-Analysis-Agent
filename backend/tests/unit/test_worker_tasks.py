"""The task in Celery's local mode (.apply runs it at once), with Postgres and Redis replaced
by small fakes that record every call: no worker, no database, no Redis, no cost."""

import json
from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from adaa.agent.state import FinishedAnswer
from adaa.worker import tasks
from adaa.worker.events import ProgressEvent
from tests.unit.fakes import fake_context, query_result

QID = uuid4()


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Fake context, table and stream; returns the list of table/stream calls, in order."""
    form = json.dumps({"metric": "revenue"})
    sentence = json.dumps({"answer_text": "Revenue was R$ 100.00."})
    context, _ = fake_context(form, sentence)
    context = replace(context, ask=lambda form: query_result((Decimal(100),)))
    monkeypatch.setattr(tasks, "get_context", lambda: context)

    log: list[tuple[str, Any]] = []
    monkeypatch.setattr(tasks.questions, "mark_running", lambda qid: log.append(("running", qid)))
    monkeypatch.setattr(tasks.questions, "mark_failed", lambda qid: log.append(("failed", qid)))
    monkeypatch.setattr(
        tasks.questions, "save_answer", lambda qid, answer: log.append(("saved", answer))
    )
    monkeypatch.setattr(tasks.events, "publish", lambda qid, event: log.append(("event", event)))
    return log


def run() -> dict[str, Any]:
    result = tasks.answer_question.apply(args=(str(QID), "Total revenue")).get()
    assert isinstance(result, dict)
    return result


def test_the_row_and_the_events_follow_the_question(calls: list[tuple[str, Any]]) -> None:
    result = run()
    assert result == {"question_id": str(QID), "status": "answered"}  # the answer is in Postgres
    kinds = [
        (name, value.kind if isinstance(value, ProgressEvent) else None) for name, value in calls
    ]
    assert kinds == [
        ("running", None),
        ("event", "step"),
        ("event", "step"),
        ("event", "step"),
        ("saved", None),
        ("event", "done"),
    ]
    texts = [value.text for name, value in calls if name == "event" and value.kind == "step"]
    assert texts == list(tasks.STEP_TEXT.values())
    saved = next(value for name, value in calls if name == "saved")
    assert isinstance(saved, FinishedAnswer) and saved.text == "Revenue was R$ 100.00."
    assert calls[0] == ("running", QID)


def test_the_soft_time_limit_saves_a_job_timeout_answer(
    calls: list[tuple[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def too_slow(question: str, context: object, on_step: object) -> FinishedAnswer:
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(tasks, "ask", too_slow)
    run()
    saved = next(value for name, value in calls if name == "saved")
    assert saved.error_kind == "job_timeout" and saved.text == tasks.TIMEOUT_TEXT
    assert calls[-1] == ("event", ProgressEvent(kind="done"))


def test_a_crash_marks_failed_and_tells_the_ui(
    calls: list[tuple[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(question: str, context: object, on_step: object) -> FinishedAnswer:
        raise RuntimeError("a bug")

    monkeypatch.setattr(tasks, "ask", broken)
    outcome = tasks.answer_question.apply(args=(str(QID), "Total revenue"))
    assert outcome.failed()  # Celery records the crash too
    assert calls[-2:] == [
        ("failed", QID),
        ("event", ProgressEvent(kind="failed", text=tasks.CRASH_TEXT)),
    ]


def test_warm_up_loads_the_context(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[bool] = []
    monkeypatch.setattr(tasks, "get_context", lambda: loaded.append(True))
    tasks.warm_up()
    assert loaded == [True]


def test_the_task_has_a_stable_name() -> None:
    assert tasks.answer_question.name == "adaa.answer_question"  # the API sends jobs by name


def test_the_success_log_line_never_holds_the_answer() -> None:
    from celery.app import trace

    assert "return_value" not in trace.LOG_SUCCESS  # names and run time only
    assert "%(id)s" in trace.LOG_SUCCESS and "%(runtime)s" in trace.LOG_SUCCESS


def test_question_ids_are_uuids() -> None:
    assert isinstance(QID, UUID)
