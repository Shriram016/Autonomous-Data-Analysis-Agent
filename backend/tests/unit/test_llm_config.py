from pathlib import Path

import pytest

from adaa.llm.config import CONFIG_FILE, LlmConfigError, load


def broken_copy(tmp_path: Path, old: str, new: str) -> Path:
    """A copy of the real config/llm.yaml with one text change."""
    text = CONFIG_FILE.read_text(encoding="utf-8")
    assert old in text, f"test setup: '{old}' not found in llm.yaml"
    path = tmp_path / "llm.yaml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


def test_real_config_loads() -> None:
    agent = load().job_settings("agent")
    assert agent.model_name == "claude-haiku-5-5"
    assert agent.settings.thinking == "disabled"  # §0 M1.2: start with thinking off
    assert agent.provider.adapter == "anthropic"
    assert agent.provider.api_key_env == "ANTHROPIC_API_KEY"
    assert agent.model.price_per_million.output == 0.50
    assert agent.settings.max_attempts == 2 and agent.settings.max_rows is None

    answer = load().job_settings("answer")
    assert answer.settings.max_attempts == 1  # no retry: the template answer is the fallback
    assert answer.settings.max_rows == 20


def test_unknown_job_gives_a_clear_error() -> None:
    with pytest.raises(LlmConfigError, match="No LLM job called 'agnet'"):
        load().job_settings("agnet")


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("model: claude-haiku-5-5", "model: claude-haiku-9", "unknown model 'claude-haiku-9'"),
        ("provider: anthropic", "provider: acme", "unknown provider 'acme'"),
        ("thinking: disabled", "thinking: maybe", "thinking"),
        ("thinking: disabled", "thinking: off", "thinking"),  # YAML reads bare off as false
        ("max_tokens: 2000", "max_tokens: 0", "max_tokens"),
        ("timeout_seconds: 30", "timeout_secs: 30", "timeout_secs"),  # typo in a key
        ("max_attempts: 2", "max_attempts: 3", "max_attempts"),  # never more than one retry
        ("max_attempts: 1", "max_attempts: 0", "max_attempts"),
        ("max_rows: 20", "max_rows: 0", "max_rows"),
    ],
)
def test_wrong_config_does_not_load(tmp_path: Path, old: str, new: str, message: str) -> None:
    with pytest.raises(LlmConfigError, match=message):
        load(broken_copy(tmp_path, old, new))


def test_router_order_is_config() -> None:
    config = load()
    assert config.router.order == ["route_jev", "route_haiku"]  # Jev first, Haiku fallback
    jev = config.job_settings("route_jev")
    assert jev.provider.adapter == "jev" and jev.provider.api_key_env == "OPENROUTER_API_KEY"
    assert jev.model_name == "typesafe/jev-1.14"  # pinned, not jev-latest


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("order: [route_jev, route_haiku]", "order: [route_jev, route_gpt]", "unknown job"),
        ("    max_tokens: 100  # one short field\n", "", "needs max_tokens"),
    ],
)
def test_wrong_router_config_does_not_load(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    with pytest.raises(LlmConfigError, match=message):
        load(broken_copy(tmp_path, old, new))
