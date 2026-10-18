"""All runtime settings, loaded and validated once at startup.

Values come from environment variables prefixed ``ADAA_``, or from the repo-root ``.env``
file. A missing or invalid required value raises at startup instead of failing mid-question.
"""

from pathlib import Path
from typing import Literal

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


def get_settings() -> Settings:
    return Settings()  # values come from env / .env, not arguments
