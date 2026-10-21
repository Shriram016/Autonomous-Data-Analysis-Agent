import pytest

from adaa.llm.adapters.base import Adapter, Message
from adaa.llm.adapters.fake import FakeAdapter
from adaa.llm.config import load
from adaa.llm.types import LlmUnavailableError

AGENT = load().job_settings("agent")
ASK = [Message(role="user", content="revenue by state")]


def test_replies_come_in_order_and_calls_are_recorded() -> None:
    fake = FakeAdapter(["first", "second"])
    adapter: Adapter = fake  # the fake has the adapter shape (mypy checks this line)

    assert adapter.send(ASK, {"type": "object"}, AGENT).text == "first"
    assert adapter.send(ASK, {}, AGENT).text == "second"
    assert len(fake.calls) == 2
    assert fake.calls[0].messages == ASK and fake.calls[0].schema == {"type": "object"}


def test_a_scripted_error_is_raised() -> None:
    fake = FakeAdapter([LlmUnavailableError("The AI service is down.")])
    with pytest.raises(LlmUnavailableError, match="down"):
        fake.send(ASK, {}, AGENT)


def test_fake_usage_uses_the_job_price() -> None:
    reply = FakeAdapter(["{}"]).send(ASK, {}, AGENT)
    # 1,000 in x $0.10/M + 100 out x $0.50/M (Haiku 5.5)
    assert reply.usage.cost_usd == pytest.approx(0.00015)
