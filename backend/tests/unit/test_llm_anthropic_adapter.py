"""The Anthropic adapter with a fake client: no network, no key, no cost."""

import copy
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from adaa.llm.adapters import anthropic_adapter
from adaa.llm.adapters.anthropic_adapter import AnthropicAdapter, clean_schema
from adaa.llm.adapters.base import Message
from adaa.llm.config import load
from adaa.llm.types import LlmOutputError, LlmUnavailableError
from adaa.semantic_layer.request import StructuredRequest

AGENT = load().job_settings("agent")
ASK = [
    Message(role="system", content="You fill the form."),
    Message(role="user", content="Revenue by state in 2017"),
]
SCHEMA = StructuredRequest.model_json_schema()
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class FakeClient:
    """Records the request instead of sending it; returns a scripted response or error."""

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.sent: dict[str, Any] = {}
        self.messages = SimpleNamespace(create=self.create)
        self.response, self.error = response, error

    def create(self, **kwargs: Any) -> Any:
        self.sent = kwargs
        if self.error:
            raise self.error
        return self.response


def reply(text: str = '{"metric": "revenue"}', stop: str = "end_turn", thinking: int = 0) -> Any:
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=3_000,
            output_tokens=300,
            output_tokens_details=SimpleNamespace(thinking_tokens=thinking),
        ),
    )


def send(client: FakeClient) -> Any:
    return AnthropicAdapter(client=client).send(ASK, SCHEMA, AGENT)


def test_request_is_built_from_the_config() -> None:
    client = FakeClient(reply())
    send(client)
    sent = client.sent
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["max_tokens"] == 2000 and sent["timeout"] == 30.0
    assert sent["system"] == "You fill the form."  # split out of the messages
    assert sent["messages"] == [{"role": "user", "content": "Revenue by state in 2017"}]
    assert sent["thinking"] == {"type": "disabled"}
    assert "effort" not in sent["output_config"]
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["output_config"]["format"]["schema"] == clean_schema(SCHEMA)


def test_thinking_on_sends_adaptive_with_effort() -> None:
    low = AGENT.model_copy(
        update={"settings": AGENT.settings.model_copy(update={"thinking": "low"})}
    )
    client = FakeClient(reply())
    AnthropicAdapter(client=client).send(ASK, SCHEMA, low)
    assert client.sent["thinking"] == {"type": "adaptive"}
    assert client.sent["output_config"]["effort"] == "low"


def test_usage_is_read_with_thinking_tokens() -> None:
    result = send(FakeClient(reply(thinking=120)))
    assert result.text == '{"metric": "revenue"}'
    assert (result.usage.input_tokens, result.usage.output_tokens) == (3_000, 300)
    assert result.usage.thinking_tokens == 120
    assert result.usage.cost_usd == pytest.approx(0.00045)


@pytest.mark.parametrize(
    ("stop", "message"), [("refusal", "declined"), ("max_tokens", "increase max_tokens")]
)
def test_bad_stop_reasons_are_clear_errors(stop: str, message: str) -> None:
    with pytest.raises(LlmOutputError, match=message):
        send(FakeClient(reply(stop=stop)))


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (anthropic.APITimeoutError(request=REQUEST), "took too long"),
        (anthropic.APIConnectionError(request=REQUEST), "could not be reached"),
        (
            anthropic.RateLimitError(
                "busy", response=httpx2.Response(429, request=REQUEST), body=None
            ),
            "rate limit",
        ),
        (
            anthropic.InternalServerError(
                "down", response=httpx2.Response(500, request=REQUEST), body=None
            ),
            r"error \(500\)",
        ),
    ],
)
def test_sdk_errors_become_unavailable(error: Exception, message: str) -> None:
    with pytest.raises(LlmUnavailableError, match=message):
        send(FakeClient(error=error))


def test_missing_key_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(anthropic_adapter, "read_secret", lambda name: None)
    with pytest.raises(LlmUnavailableError, match="ANTHROPIC_API_KEY is not set"):
        AnthropicAdapter().send(ASK, SCHEMA, AGENT)


def test_clean_schema_removes_only_unsupported_rules() -> None:
    schema = {
        "type": "object",
        "properties": {
            "minimum": {"type": "integer", "minimum": 1, "maximum": 9},  # a field NAMED minimum
            "tags": {"type": "array", "items": {"type": "string", "minLength": 1}, "maxItems": 2},
        },
        "required": ["minimum"],
    }
    original = copy.deepcopy(schema)
    assert clean_schema(schema) == {
        "type": "object",
        "properties": {
            "minimum": {"type": "integer"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["minimum"],
        "additionalProperties": False,
    }
    assert "maxItems" not in str(clean_schema(SCHEMA))
    assert schema == original  # the original is not changed
