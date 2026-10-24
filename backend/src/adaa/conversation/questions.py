"""The questions table: one row per question, from submit to answer (§0 M1.5).

The API creates the row (so an unknown id is really unknown), the worker marks it running and
saves the answer with its usage (the durable usage record). Every function logs in as
adaa_app, which can read and write only the `conversation` schema.

Owner check: get_question returns None both for an id that doesn't exist and for someone
else's question, so nobody can learn that another user's question exists.

Jobs can run twice ("at least once", M1.4), so the writes are safe to repeat: a second
mark_running never moves a finished question back to running.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

from adaa.agent.state import FinishedAnswer
from adaa.settings import get_settings

QuestionState = Literal["waiting", "running", "done", "failed"]

LOCAL_OWNER = "local-dev"  # every question's owner until login exists (M6, §0)


class QuestionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    owner: str
    question: str
    state: QuestionState
    answer: FinishedAnswer | None
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    cost_usd: Decimal
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    wait_seconds: Decimal | None  # worked out by Postgres
    total_seconds: Decimal | None


def connect(conninfo: str | None = None) -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(
        conninfo or get_settings().postgres_conninfo("app"), row_factory=dict_row
    )


def create_question(owner: str, question: str, conninfo: str | None = None) -> UUID:
    with connect(conninfo) as conn:
        row = conn.execute(
            "INSERT INTO conversation.questions (owner, question) VALUES (%s, %s) RETURNING id",
            (owner, question),
        ).fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def mark_running(question_id: UUID, conninfo: str | None = None) -> None:
    with connect(conninfo) as conn:
        conn.execute(
            "UPDATE conversation.questions SET state = 'running', started_at = now() "
            "WHERE id = %s AND state IN ('waiting', 'running')",  # never undo a finished one
            (question_id,),
        )


def save_answer(question_id: UUID, answer: FinishedAnswer, conninfo: str | None = None) -> None:
    """The job ended: store the answer (answered OR a plain failure message) and its usage."""
    usage = answer.usage
    with connect(conninfo) as conn:
        conn.execute(
            "UPDATE conversation.questions SET state = 'done', answer = %s, "
            "input_tokens = %s, output_tokens = %s, thinking_tokens = %s, cost_usd = %s, "
            "finished_at = now() WHERE id = %s",
            (
                Jsonb(answer.model_dump(mode="json")),
                usage.input_tokens,
                usage.output_tokens,
                usage.thinking_tokens,
                usage.cost_usd,
                question_id,
            ),
        )


def mark_failed(question_id: UUID, conninfo: str | None = None) -> None:
    """The job itself crashed and there is no answer at all."""
    with connect(conninfo) as conn:
        conn.execute(
            "UPDATE conversation.questions SET state = 'failed', finished_at = now() "
            "WHERE id = %s AND state <> 'done'",
            (question_id,),
        )


def get_question(
    question_id: UUID, owner: str, conninfo: str | None = None
) -> QuestionRecord | None:
    with connect(conninfo) as conn:
        row = conn.execute(
            "SELECT * FROM conversation.questions WHERE id = %s AND owner = %s",
            (question_id, owner),
        ).fetchone()
    return QuestionRecord.model_validate(row) if row else None
