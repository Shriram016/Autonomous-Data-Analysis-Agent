"""How Alembic connects: as the owner role, with the settings from .env.

Migrations create and change tables, so they run as adaa_owner (the app itself never can).
The `alembic_version` bookkeeping table stays in the `public` schema, outside `conversation`,
so adaa_app (which may write `conversation`) can never change which migrations ran.
"""

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from adaa.settings import get_settings


def owner_url() -> URL:
    settings = get_settings()
    return URL.create(
        "postgresql+psycopg",
        username=settings.db_user,
        password=settings.db_password.get_secret_value(),
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        query={"connect_timeout": str(settings.db_connect_timeout_s)},
    )


def run_migrations() -> None:
    engine = create_engine(owner_url())
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():  # a failed migration leaves nothing half-done
            context.run_migrations()


run_migrations()
