"""The questions table and the adaa_app role (needs docker compose up + `alembic upgrade head`)."""

import psycopg
import pytest

from adaa.settings import get_settings

pytestmark = pytest.mark.integration


def as_app() -> psycopg.Connection:
    return psycopg.connect(get_settings().postgres_conninfo("app"))


def test_app_role_writes_a_question_and_the_times_fill_in() -> None:
    with as_app() as conn:  # rolled back at the end: no row is left behind
        row = conn.execute(
            "INSERT INTO conversation.questions (owner, question) VALUES ('test', 'Total revenue') "
            "RETURNING id, state, wait_seconds, total_seconds"
        ).fetchone()
        assert row is not None
        question_id, state, wait, total = row
        assert state == "waiting" and wait is None and total is None  # no times yet
        conn.execute(
            "UPDATE conversation.questions SET started_at = created_at + interval '2 seconds', "
            "finished_at = created_at + interval '7 seconds', state = 'done' WHERE id = %s",
            (question_id,),
        )
        times = conn.execute(
            "SELECT wait_seconds, total_seconds FROM conversation.questions WHERE id = %s",
            (question_id,),
        ).fetchone()
        assert times == (2, 7)  # worked out by Postgres from the times
        conn.rollback()


def test_the_database_refuses_an_unknown_state() -> None:
    with as_app() as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO conversation.questions (owner, question, state) "
            "VALUES ('test', 'x', 'maybe')"
        )


def test_app_role_cannot_read_business_data() -> None:
    with as_app() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT count(*) FROM business.orders")


def test_app_role_cannot_delete_or_change_the_migration_record() -> None:
    with as_app() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("DELETE FROM conversation.questions")
    with as_app() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("UPDATE public.alembic_version SET version_num = '9999'")
