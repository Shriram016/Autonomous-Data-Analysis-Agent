"""All runtime settings, loaded and validated once at startup.

Values come from environment variables prefixed ``ADAA_``, or from the repo-root ``.env``
file. A missing or invalid required value raises at startup instead of failing mid-question.
"""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# settings.py → adaa → src → backend → repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# Database roles are named after the job that uses them (§0, Database access).
DbRole = Literal["owner", "loader", "query"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ADAA_",
        env_file=REPO_ROOT / ".env",
        extra="ignore",  # the .env may hold settings for other tools
    )

    app_env: Literal["local", "prod"]  # required: no default on purpose
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Postgres (same values docker-compose uses)
    db_host: str = "127.0.0.1"  # not "localhost": Windows may try IPv6 first and hang
    db_port: int = 5433  # 5433: a local Windows Postgres often owns 5432
    db_name: str = "adaa"
    db_user: str = "adaa_owner"  # the owner role: setup and migrations only
    db_password: SecretStr  # required; SecretStr keeps it out of logs and reprs
    db_loader_password: SecretStr | None = None  # only the load / ingestion job needs it
    db_query_password: SecretStr | None = None  # the agent's read-only queries

    db_connect_timeout_s: int = 2  # locked in the failure design: fail fast, never hang

    redis_url: str = "redis://127.0.0.1:6379/0"

    def postgres_conninfo(self, role: DbRole = "owner") -> str:
        """Connection string for psycopg, logging in as the given role."""
        if role == "owner":
            user, password = self.db_user, self.db_password
        else:
            role_password = {"loader": self.db_loader_password, "query": self.db_query_password}
            found = role_password[role]
            if found is None:
                raise ValueError(f"ADAA_DB_{role.upper()}_PASSWORD is not set in .env")
            user, password = f"adaa_{role}", found
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={user} password={password.get_secret_value()} "
            f"connect_timeout={self.db_connect_timeout_s}"
        )


def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from env / .env
