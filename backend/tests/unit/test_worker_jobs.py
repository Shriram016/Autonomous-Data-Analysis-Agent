"""Submit and fetch with Celery replaced by small fakes: no worker, no Redis, no cost."""

from types import SimpleNamespace
from typing import Any

import pytest

from adaa.agent.state import NO_USAGE, FinishedAnswer, Versions
from adaa.worker import jobs
from adaa.worker.celery_app import app

ANSWER = FinishedAnswer(
    question="Total revenue",
    status="answered",
    text="Revenue was R$ 100.00.",
    versions=Versions(
        semantic_layer="0.3.3 (x)", agent_prompt="0.1.0 (y)", answer_prompt="0.1.0 (z)"
    ),
    usage=NO_USAGE,
)


def fake_result(monkeypatch: pytest.MonkeyPatch, state: str, result: Any = None) -> None:
    monkeypatch.setattr(
        jobs, "AsyncResult", lambda job_id, app: SimpleNamespace(state=state, result=result)
    )


def test_submit_returns_the_job_number_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    def delay(question: str) -> SimpleNamespace:
        sent.append(question)
        return SimpleNamespace(id="job-123")

    monkeypatch.setattr(jobs.answer_question, "delay", delay)
    assert jobs.submit("Total revenue") == "job-123"
    assert sent == ["Total revenue"]


@pytest.mark.parametrize(
    ("celery_state", "state"),
    [("PENDING", "waiting"), ("RETRY", "waiting"), ("STARTED", "running"), ("FAILURE", "failed")],
)
def test_celery_states_become_plain_states(
    monkeypatch: pytest.MonkeyPatch, celery_state: str, state: str
) -> None:
    fake_result(monkeypatch, celery_state)
    status = jobs.get_result("job-123")
    assert status.state == state and status.answer is None


def test_done_carries_the_finished_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_result(monkeypatch, "SUCCESS", ANSWER.model_dump(mode="json"))  # as Redis returns it
    status = jobs.get_result("job-123")
    assert status.state == "done" and status.answer == ANSWER


def test_results_are_kept_in_redis_for_one_day() -> None:
    assert app.conf.result_backend == app.conf.broker_url
    assert app.conf.result_expires == 24 * 60 * 60
    assert app.conf.task_track_started is True
