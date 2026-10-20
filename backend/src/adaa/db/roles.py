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
    # Set on the role itself, so no code path can skip it.
    conn.execute(
        sql.SQL("ALTER ROLE adaa_query SET statement_timeout = {}").format(
            sql.Literal(QUERY_STATEMENT_TIMEOUT)
        )
    )


def main() -> None:
    settings = get_settings()
    passwords = {
        "ADAA_DB_LOADER_PASSWORD": settings.db_loader_password,
        "ADAA_DB_QUERY_PASSWORD": settings.db_query_password,
    }
    missing = [name for name, value in passwords.items() if value is None]
    if missing:
        raise SystemExit(f"Set {', '.join(missing)} in .env first.")
    assert settings.db_loader_password and settings.db_query_password
    with psycopg.connect(settings.postgres_conninfo("owner")) as conn:
        setup_loader_role(conn, settings.db_loader_password.get_secret_value())
        setup_query_role(conn, settings.db_query_password.get_secret_value())
    print("Role adaa_loader ready: USAGE + CREATE on schemas staging, business.")
    print(f"Role adaa_query ready: SELECT on business only, timeout {QUERY_STATEMENT_TIMEOUT}.")


if __name__ == "__main__":
    main()
