"""Submit and fetch with the table and Celery replaced by small fakes: no database, no Redis."""

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from adaa.worker import jobs

QID = uuid4()


def test_submit_creates_the_row_first_and_uses_its_id_as_the_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    queued: dict[str, Any] = {}

    def create_question(owner: str, question: str) -> UUID:
        order.append("row")
        return QID

    def apply_async(args: tuple[str, str], task_id: str) -> SimpleNamespace:
        order.append("queue")
        queued.update(args=args, task_id=task_id)
        return SimpleNamespace(id=task_id)

    monkeypatch.setattr(jobs.questions, "create_question", create_question)
    monkeypatch.setattr(jobs.answer_question, "apply_async", apply_async)

    assert jobs.submit("local-dev", "Total revenue") == QID
    assert order == ["row", "queue"]  # the row exists before any worker can see the job
    assert queued == {"args": (str(QID), "Total revenue"), "task_id": str(QID)}  # one id


def test_get_result_reads_the_row_with_the_owner_check(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[UUID, str]] = []

    def get_question(question_id: UUID, owner: str) -> None:
        asked.append((question_id, owner))
        return None  # unknown, or someone else's

    monkeypatch.setattr(jobs.questions, "get_question", get_question)
    assert jobs.get_result(QID, "someone-else") is None
    assert asked == [(QID, "someone-else")]
