import pytest
from pydantic import ValidationError

from adaa.settings import Settings


def load_without_env_file() -> Settings:
    # Ignore the developer's real .env so tests only see what they set.
    return Settings(_env_file=None)


def test_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAA_APP_ENV", "local")
    settings = load_without_env_file()
    assert settings.app_env == "local"
    assert settings.log_level == "INFO"


def test_missing_required_value_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADAA_APP_ENV", raising=False)
    with pytest.raises(ValidationError, match="app_env"):
        load_without_env_file()


def test_invalid_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAA_APP_ENV", "staging")
    with pytest.raises(ValidationError):
        load_without_env_file()
