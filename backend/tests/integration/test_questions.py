"""The question functions on real Postgres (needs docker compose up + `alembic upgrade head`)."""

from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from adaa.agent.state import FinishedAnswer, Versions
from adaa.conversation import questions as q
from adaa.llm.types import Usage
from adaa.settings import get_settings

pytestmark = pytest.mark.integration

ANSWER = FinishedAnswer(
    question="Total revenue",
    status="answered",
    text="Revenue was R$ 13,221,498.11.",
    versions=Versions(
        semantic_layer="0.3.3 (x)", agent_prompt="0.1.0 (y)", answer_prompt="0.1.0 (z)"
    ),
    usage=Usage(input_tokens=4_961, output_tokens=40, thinking_tokens=0, cost_usd=0.000516),
)


@pytest.fixture
def owner() -> Iterator[str]:
    """A test owner of its own; its rows are removed afterwards (adaa_app can't delete)."""
    name = f"test-{uuid4()}"
    yield name
    with psycopg.connect(get_settings().postgres_conninfo("owner")) as conn:
        conn.execute("DELETE FROM conversation.questions WHERE owner = %s", (name,))


def test_full_life_cycle(owner: str) -> None:
    question_id = q.create_question(owner, "Total revenue")
    first = q.get_question(question_id, owner)
    assert first is not None and first.state == "waiting" and first.answer is None

    q.mark_running(question_id)
    running = q.get_question(question_id, owner)
    assert running is not None and running.state == "running" and running.started_at is not None
    assert running.wait_seconds is not None

    q.save_answer(question_id, ANSWER)
    done = q.get_question(question_id, owner)
    assert done is not None and done.state == "done"
    assert done.answer == ANSWER  # the whole answer comes back from the JSON
    assert (done.input_tokens, done.output_tokens) == (4_961, 40)
    assert done.cost_usd == Decimal("0.000516")
    assert done.total_seconds is not None and done.total_seconds >= done.wait_seconds  # type: ignore[operator]


def test_a_crashed_job_is_failed(owner: str) -> None:
    question_id = q.create_question(owner, "Total revenue")
    q.mark_running(question_id)
    q.mark_failed(question_id)
    failed = q.get_question(question_id, owner)
    assert failed is not None and failed.state == "failed" and failed.answer is None


def test_a_repeated_run_never_undoes_a_finished_question(owner: str) -> None:
    question_id = q.create_question(owner, "Total revenue")
    q.save_answer(question_id, ANSWER)
    q.mark_running(question_id)  # a second delivery of the same job (at least once)
    q.mark_failed(question_id)
    record = q.get_question(question_id, owner)
    assert record is not None and record.state == "done"


def test_another_owner_and_an_unknown_id_both_get_nothing(owner: str) -> None:
    question_id = q.create_question(owner, "Total revenue")
    assert q.get_question(question_id, "someone-else") is None
    assert q.get_question(uuid4(), owner) is None
