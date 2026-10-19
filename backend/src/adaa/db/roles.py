"""Create the database roles a slice needs, and grant each one only its own schemas.

Runs as the owner role. Safe to run again: an existing role only gets its password updated.

Run from backend/:  uv run python -m adaa.db.roles
"""

import psycopg
from psycopg import sql

from adaa.settings import get_settings


def setup_loader_role(conn: psycopg.Connection, password: str) -> None:
    """adaa_loader: writes `staging`, publishes into `business`. Nothing else."""
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'adaa_loader'").fetchone()
    verb = "ALTER" if exists else "CREATE"
    # Role statements can't take bound parameters, so the password is quoted safely instead.
    conn.execute(
        sql.SQL(verb + " ROLE adaa_loader WITH LOGIN PASSWORD {}").format(sql.Literal(password))
    )
    # USAGE = may look inside the schema; CREATE = may create tables there (and owns them).
    conn.execute("GRANT USAGE, CREATE ON SCHEMA staging, business TO adaa_loader")


def main() -> None:
    settings = get_settings()
    if settings.db_loader_password is None:
        raise SystemExit("Set ADAA_DB_LOADER_PASSWORD in .env first.")
    with psycopg.connect(settings.postgres_conninfo("owner")) as conn:
        setup_loader_role(conn, settings.db_loader_password.get_secret_value())
    print("Role adaa_loader ready: USAGE + CREATE on schemas staging, business.")


if __name__ == "__main__":
    main()
