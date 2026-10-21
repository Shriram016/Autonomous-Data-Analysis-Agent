"""The shape every adapter has (ADR 0009: ports and adapters).

An adapter is the only code that talks to a provider. llm.complete calls send() and gets
an AdapterReply back; it never knows which provider answered. The adapter does NOT check
the reply against the form; llm.complete does that, in one place for every adapter.
"""

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from adaa.llm.config import JobSettings
from adaa.llm.types import AdapterReply


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class Adapter(Protocol):
    def send(
        self, messages: list[Message], schema: dict[str, Any], job: JobSettings
    ) -> AdapterReply:
        """Send the messages and the form's JSON schema; return the raw reply.

        Raises LlmUnavailableError with a plain message when the provider can't answer.
        """
        ...
