"""adaa_query reads business, writes nothing, sees nothing else, and stops after 5 s.

Needs: docker compose up, and `python -m adaa.db.roles` run once.
"""

import psycopg
import pytest

from adaa.settings import get_settings

pytestmark = pytest.mark.integration


def query_conn() -> psycopg.Connection:
    return psycopg.connect(get_settings().postgres_conninfo("query"), autocommit=True)


def test_can_read_business() -> None:
    with query_conn() as conn:
        row = conn.execute("SELECT count(*) FROM business.orders").fetchone()
    assert row is not None and row[0] > 0


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO business.orders (order_id) VALUES ('should-not-exist')",
        "DELETE FROM business.orders",
        "DROP TABLE business.orders",
        "CREATE TABLE business.sneaky (x int)",
    ],
)
def test_cannot_change_anything(statement: str) -> None:
    with query_conn() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)


def test_cannot_see_other_schemas() -> None:
    with query_conn() as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT count(*) FROM pg_catalog.pg_tables, staging.orders")


def test_statement_timeout_is_5_seconds() -> None:
    with query_conn() as conn:
        row = conn.execute("SHOW statement_timeout").fetchone()
        assert row == ("5s",)
        with pytest.raises(psycopg.errors.QueryCanceled):
            conn.execute("SELECT pg_sleep(6)")


def test_new_tables_from_the_loader_will_be_readable() -> None:
    """The daily load replaces tables; a default privilege grants read on each new one."""
    with psycopg.connect(get_settings().postgres_conninfo("owner")) as conn:
        rows = conn.execute(
            "SELECT n.nspname FROM pg_default_acl d "
            "JOIN pg_roles r ON r.oid = d.defaclrole "
            "JOIN pg_namespace n ON n.oid = d.defaclnamespace "
            "WHERE r.rolname = 'adaa_loader' AND d.defaclacl::text LIKE '%adaa_query=r/%'"
        ).fetchall()
    assert {r[0] for r in rows} == {"staging", "business"}
