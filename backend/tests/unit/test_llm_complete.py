import json

import pytest

from adaa.llm.adapters.base import Message
from adaa.llm.adapters.fake import FakeAdapter
from adaa.llm.complete import complete
from adaa.llm.config import LlmConfigError
from adaa.llm.types import LlmOutputError, LlmResult, LlmUnavailableError
from adaa.semantic_layer.request import StructuredRequest

ASK = [Message(role="user", content="Revenue by state in 2017")]
GOOD = json.dumps({"metric": "revenue", "dimensions": ["customer_state"]})


def ask(fake: FakeAdapter, job: str = "agent") -> LlmResult[StructuredRequest]:
    return complete(job, ASK, StructuredRequest, adapter=fake)


def test_good_first_reply() -> None:
    fake = FakeAdapter([GOOD])
    result = ask(fake)
    assert isinstance(result.output, StructuredRequest)
    assert result.output.metric == "revenue"
    assert result.output.dimensions == ["customer_state"]
    assert result.attempts == 1
    assert result.model_name == "claude-haiku-5-5"
    assert fake.calls[0].schema == StructuredRequest.model_json_schema()


def test_bad_json_then_good_reply() -> None:
    fake = FakeAdapter(["not json", GOOD])
    result = ask(fake)
    assert result.attempts == 2
    retry = fake.calls[1].messages
    assert retry[:1] == ASK  # the original question is kept
    assert retry[1] == Message(role="assistant", content="not json")
    assert "did not match the required form" in retry[2].content
    assert "Invalid JSON" in retry[2].content  # the real error is sent back


def test_wrong_field_is_retried() -> None:
    wrong = json.dumps({"metric": 42})
    unknown = json.dumps({"metric": "revenue", "colour": "red"})  # extra="forbid"
    for bad in (wrong, unknown):
        fake = FakeAdapter([bad, GOOD])
        assert ask(fake).attempts == 2


def test_two_bad_replies_raise_a_clear_error() -> None:
    fake = FakeAdapter(["not json", "{still not json"])
    with pytest.raises(LlmOutputError, match="after 2 tries"):
        ask(fake)
    assert len(fake.calls) == 2  # never a third try


def test_outage_is_not_retried() -> None:
    fake = FakeAdapter([LlmUnavailableError("The AI service is down."), GOOD])
    with pytest.raises(LlmUnavailableError, match="down"):
        ask(fake)
    assert len(fake.calls) == 1


def test_retry_usage_is_added() -> None:
    once = ask(FakeAdapter([GOOD])).usage
    twice = ask(FakeAdapter(["not json", GOOD])).usage
    assert twice.input_tokens == 2 * once.input_tokens
    assert twice.cost_usd == pytest.approx(2 * once.cost_usd)


def test_unknown_job() -> None:
    with pytest.raises(LlmConfigError, match="No LLM job called 'agnet'"):
        ask(FakeAdapter([GOOD]), job="agnet")


# --- usage log (step 5) ---


def llm_lines(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    return [r.llm for r in caplog.records if r.name == "adaa.llm"]  # type: ignore[attr-defined]


def test_good_call_writes_one_ok_line(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="adaa.llm")
    ask(FakeAdapter([GOOD]))
    [line] = llm_lines(caplog)
    assert line["job"] == "agent" and line["model"] == "claude-haiku-5-5"
    assert line["outcome"] == "ok" and line["attempts"] == 1
    assert (line["input_tokens"], line["output_tokens"]) == (1_000, 100)  # the fake's counts
    assert line["cost_usd"] == pytest.approx(0.00015)


def test_output_error_line_has_both_attempts(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="adaa.llm")
    with pytest.raises(LlmOutputError):
        ask(FakeAdapter(["not json", "not json"]))
    [line] = llm_lines(caplog)
    assert line["outcome"] == "output_error" and line["attempts"] == 2
    assert line["input_tokens"] == 2_000  # a failed call still costs money


def test_outage_line(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="adaa.llm")
    with pytest.raises(LlmUnavailableError):
        ask(FakeAdapter([LlmUnavailableError("down")]))
    [line] = llm_lines(caplog)
    assert line["outcome"] == "unavailable" and line["attempts"] == 0


def test_log_never_holds_the_question_or_reply(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="adaa.llm")
    ask(FakeAdapter(["not json", GOOD]))
    assert "Revenue by state" not in caplog.text
    assert "customer_state" not in caplog.text and "not json" not in caplog.text
