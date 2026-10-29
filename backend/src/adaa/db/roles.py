"""Create the database roles a slice needs, and grant each one only its own schemas.

Runs as the owner role. Safe to run again: an existing role only gets its password updated.

Run from backend/:  uv run python -m adaa.db.roles
"""

import psycopg
from psycopg import sql

from adaa.settings import get_settings

QUERY_STATEMENT_TIMEOUT = "5s"  # locked in the failure design (§0): one query may run 5 s at most


def create_or_update_login(conn: psycopg.Connection, role: str, password: str) -> None:
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
    verb = "ALTER" if exists else "CREATE"
    # Role statements can't take bound parameters, so names and passwords are quoted safely.
    conn.execute(
        sql.SQL(verb + " ROLE {} WITH LOGIN PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(password)
        )
    )


def setup_loader_role(conn: psycopg.Connection, password: str) -> None:
    """adaa_loader: writes `staging`, publishes into `business`. Nothing else."""
    create_or_update_login(conn, "adaa_loader", password)
    # USAGE = may look inside the schema; CREATE = may create tables there (and owns them).
    conn.execute("GRANT USAGE, CREATE ON SCHEMA staging, business TO adaa_loader")


def setup_query_role(conn: psycopg.Connection, password: str) -> None:
    """adaa_query: the agent's queries. Read-only on `business`, 5 s per query. Nothing else."""
    create_or_update_login(conn, "adaa_query", password)
    conn.execute("GRANT USAGE ON SCHEMA business TO adaa_query")
    conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA business TO adaa_query")
    # The daily load builds new tables in staging and moves them into business (atomic swap).
    # A new table starts with no read permission, so grant it automatically for every table
    # adaa_loader creates; the permission moves with the table into business.
    for schema in ("staging", "business"):
        conn.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE adaa_loader IN SCHEMA {schema} "
            "GRANT SELECT ON TABLES TO adaa_query"
        )
    # Alembic migrations run as the owner and add business tables too (review_vectors, M3).
    conn.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE adaa_owner IN SCHEMA business "
        "GRANT SELECT ON TABLES TO adaa_query"
    )
    # Set on the role itself, so no code path can skip it.
    conn.execute(
        sql.SQL("ALTER ROLE adaa_query SET statement_timeout = {}").format(
            sql.Literal(QUERY_STATEMENT_TIMEOUT)
        )
    )


def setup_app_role(conn: psycopg.Connection, password: str) -> None:
    """adaa_app: the app's own rows (questions, later conversations). No business data."""
    create_or_update_login(conn, "adaa_app", password)
    conn.execute("GRANT USAGE ON SCHEMA conversation TO adaa_app")
    conn.execute("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA conversation TO adaa_app")
    # Alembic migrations run as the owner and create tables later; grant those automatically.
    # No DELETE: rows are kept (the usage record); deleting is a separate, deliberate job.
    conn.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE adaa_owner IN SCHEMA conversation "
        "GRANT SELECT, INSERT, UPDATE ON TABLES TO adaa_app"
    )


def setup_review_writer_role(conn: psycopg.Connection, password: str) -> None:
    """adaa_review_writer: review ingestion (M3). Reads `business`, writes only review_vectors.

    A bug in the job that calls the LLM can't touch the Olist tables. No DELETE: a rerun
    updates rows (upsert), it never removes them.
    """
    create_or_update_login(conn, "adaa_review_writer", password)
    conn.execute("GRANT USAGE ON SCHEMA business TO adaa_review_writer")
    conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA business TO adaa_review_writer")
    # The Olist reload rebuilds business.reviews, so read permission must follow new tables.
    for schema in ("staging", "business"):
        conn.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE adaa_loader IN SCHEMA {schema} "
            "GRANT SELECT ON TABLES TO adaa_review_writer"
        )
    # The table comes from migration 0002; run migrate before this script.
    if conn.execute("SELECT to_regclass('business.review_vectors')").fetchone() == (None,):
        raise SystemExit("business.review_vectors is missing: run the migrate job first.")
    conn.execute("GRANT INSERT, UPDATE ON business.review_vectors TO adaa_review_writer")


def main() -> None:
    settings = get_settings()
    passwords = {
        "ADAA_DB_LOADER_PASSWORD": settings.db_loader_password,
        "ADAA_DB_QUERY_PASSWORD": settings.db_query_password,
        "ADAA_DB_APP_PASSWORD": settings.db_app_password,
        "ADAA_DB_REVIEW_WRITER_PASSWORD": settings.db_review_writer_password,
    }
    missing = [name for name, value in passwords.items() if value is None]
    if missing:
        raise SystemExit(f"Set {', '.join(missing)} in .env first.")
    assert settings.db_loader_password and settings.db_query_password and settings.db_app_password
    assert settings.db_review_writer_password
    with psycopg.connect(settings.postgres_conninfo("owner")) as conn:
        setup_loader_role(conn, settings.db_loader_password.get_secret_value())
        setup_query_role(conn, settings.db_query_password.get_secret_value())
        setup_app_role(conn, settings.db_app_password.get_secret_value())
        setup_review_writer_role(conn, settings.db_review_writer_password.get_secret_value())
    print("Role adaa_loader ready: USAGE + CREATE on schemas staging, business.")
    print(f"Role adaa_query ready: SELECT on business only, timeout {QUERY_STATEMENT_TIMEOUT}.")
    print("Role adaa_app ready: SELECT, INSERT, UPDATE on schema conversation only.")
    print("Role adaa_review_writer ready: SELECT on business, INSERT + UPDATE on review_vectors.")


if __name__ == "__main__":
    main()
