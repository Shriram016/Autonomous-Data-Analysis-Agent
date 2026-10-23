"""The task in Celery's local mode (.apply runs it at once): no worker, no Redis, no cost."""

import json
from dataclasses import replace
from decimal import Decimal

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from adaa.agent.state import FinishedAnswer
from adaa.worker import tasks
from tests.unit.fakes import fake_context, query_result


@pytest.fixture
def use_fake_context(monkeypatch: pytest.MonkeyPatch) -> None:
    form = json.dumps({"metric": "revenue"})
    sentence = json.dumps({"answer_text": "Revenue was R$ 100.00."})
    context, _ = fake_context(form, sentence)
    context = replace(context, ask=lambda form: query_result((Decimal(100),)))
    monkeypatch.setattr(tasks, "get_context", lambda: context)


@pytest.mark.usefixtures("use_fake_context")
def test_a_question_gives_an_answered_json_result() -> None:
    result = tasks.answer_question.apply(args=("Total revenue",)).get()
    assert isinstance(result, dict)
    answer = FinishedAnswer.model_validate(result)  # the JSON turns back into the model
    assert answer.status == "answered" and answer.text == "Revenue was R$ 100.00."


@pytest.mark.usefixtures("use_fake_context")
def test_the_soft_time_limit_gives_a_job_timeout_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def too_slow(question: str, context: object) -> FinishedAnswer:
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(tasks, "ask", too_slow)
    answer = FinishedAnswer.model_validate(
        tasks.answer_question.apply(args=("Total revenue",)).get()
    )
    assert answer.status == "failed" and answer.error_kind == "job_timeout"
    assert answer.text == tasks.TIMEOUT_TEXT


def test_warm_up_loads_the_context(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[bool] = []
    monkeypatch.setattr(tasks, "get_context", lambda: loaded.append(True))
    tasks.warm_up()
    assert loaded == [True]


def test_the_task_has_a_stable_name() -> None:
    assert tasks.answer_question.name == "adaa.answer_question"  # the API sends jobs by name
