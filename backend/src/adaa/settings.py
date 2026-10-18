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
    db_user: str = "adaa"
    db_password: SecretStr  # required; SecretStr keeps it out of logs and reprs

    db_connect_timeout_s: int = 2  # locked in the failure design: fail fast, never hang

    redis_url: str = "redis://127.0.0.1:6379/0"

    def postgres_conninfo(self) -> str:
        """Connection string for psycopg."""
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={self.db_user} password={self.db_password.get_secret_value()} "
            f"connect_timeout={self.db_connect_timeout_s}"
        )


def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from env / .env
