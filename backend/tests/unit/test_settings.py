import pytest
from pydantic import ValidationError

from adaa.settings import Settings


def load_without_env_file() -> Settings:
    # Ignore the developer's real .env so tests only see what they set.
    return Settings(_env_file=None)


@pytest.fixture
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAA_APP_ENV", "local")
    monkeypatch.setenv("ADAA_DB_PASSWORD", "test-password")


@pytest.mark.usefixtures("required_env")
def test_loads_from_environment() -> None:
    settings = load_without_env_file()
    assert settings.app_env == "local"
    assert settings.log_level == "INFO"
    assert settings.redis_url == "redis://127.0.0.1:6379/0"


@pytest.mark.usefixtures("required_env")
def test_password_is_hidden_but_usable() -> None:
    settings = load_without_env_file()
    assert "test-password" not in repr(settings)
    assert "password=test-password" in settings.postgres_conninfo()


@pytest.mark.usefixtures("required_env")
def test_loader_role_needs_its_own_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADAA_DB_LOADER_PASSWORD", raising=False)
    settings = load_without_env_file()
    assert "user=adaa_owner" in settings.postgres_conninfo("owner")
    with pytest.raises(ValueError, match="ADAA_DB_LOADER_PASSWORD"):
        settings.postgres_conninfo("loader")

    monkeypatch.setenv("ADAA_DB_LOADER_PASSWORD", "loader-pw")
    assert "user=adaa_loader password=loader-pw" in load_without_env_file().postgres_conninfo(
        "loader"
    )


@pytest.mark.parametrize("missing", ["ADAA_APP_ENV", "ADAA_DB_PASSWORD"])
@pytest.mark.usefixtures("required_env")
def test_missing_required_value_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.delenv(missing)
    with pytest.raises(ValidationError):
        load_without_env_file()


@pytest.mark.usefixtures("required_env")
def test_invalid_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAA_APP_ENV", "staging")
    with pytest.raises(ValidationError):
        load_without_env_file()
