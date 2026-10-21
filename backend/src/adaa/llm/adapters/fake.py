"""A fake adapter with scripted replies: tests and fault injection at no cost (§0, item 9).

Give it the replies in order. Each send() returns the next one; a reply that is an
exception is raised instead (e.g. LlmUnavailableError to copy an outage). Every call is
recorded, so a test can check what llm.complete sent (for example, that the retry
included the validation error).
"""

from dataclasses import dataclass, field
from typing import Any

from adaa.llm.adapters.base import Message
from adaa.llm.config import JobSettings
from adaa.llm.types import AdapterReply, make_usage

FAKE_INPUT_TOKENS = 1_000  # fixed counts, so cost tests have known numbers
FAKE_OUTPUT_TOKENS = 100


@dataclass
class Call:
    messages: list[Message]
    schema: dict[str, Any]
    job: JobSettings


@dataclass
class FakeAdapter:
    replies: list[str | Exception]
    calls: list[Call] = field(default_factory=list)

    def send(
        self, messages: list[Message], schema: dict[str, Any], job: JobSettings
    ) -> AdapterReply:
        self.calls.append(Call(list(messages), schema, job))
        if not self.replies:
            raise AssertionError("FakeAdapter has no scripted reply left")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        usage = make_usage(FAKE_INPUT_TOKENS, FAKE_OUTPUT_TOKENS, 0, job.model.price_per_million)
        return AdapterReply(text=reply, usage=usage, seconds=0.0)
