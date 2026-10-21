"""Shapes that all the LLM code shares (ADR 0009).

Every adapter (fake, anthropic, later openai_compatible) returns an AdapterReply, so
llm.complete never cares which provider answered. llm.complete returns an LlmResult to
the rest of the app. Token counts are always stored, so the cost can be recomputed if a
price in config/llm.yaml was stale (§0, Cost).
"""

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from adaa.llm.config import Price


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: NonNegativeInt
    # All billed output tokens. Thinking tokens are INCLUDED here, not added on top:
    # the provider bills them as output and counts them inside output_tokens.
    output_tokens: NonNegativeInt
    thinking_tokens: NonNegativeInt = 0  # the part of output_tokens spent thinking
    cost_usd: NonNegativeFloat

    def __add__(self, other: "Usage") -> "Usage":
        """Usage of two attempts together (the first try + the retry)."""
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            thinking_tokens=self.thinking_tokens + other.thinking_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


def cost_usd(input_tokens: int, output_tokens: int, price: Price) -> float:
    """Cost of one call. output_tokens already includes the thinking tokens."""
    return (input_tokens * price.input + output_tokens * price.output) / 1_000_000


def make_usage(input_tokens: int, output_tokens: int, thinking_tokens: int, price: Price) -> Usage:
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        cost_usd=cost_usd(input_tokens, output_tokens, price),
    )


class AdapterReply(BaseModel):
    """What an adapter gives back: the raw reply text (should be JSON) and its counts."""

    model_config = ConfigDict(frozen=True)

    text: str
    usage: Usage
    seconds: NonNegativeFloat


class LlmResult[Form: BaseModel](BaseModel):
    """What llm.complete gives the rest of the app: a filled, checked form.

    Form is the job's output form, e.g. StructuredRequest.
    """

    model_config = ConfigDict(frozen=True)

    output: Form
    usage: Usage  # both attempts added together when a retry happened
    attempts: int  # 1, or 2 after one retry with the validation error
    model_name: str
    seconds: NonNegativeFloat


class LlmError(Exception):
    """Base for LLM failures. The message is plain and safe to show."""


class LlmOutputError(LlmError):
    """The reply did not match the form, even after one retry."""


class LlmUnavailableError(LlmError):
    """The provider could not answer: no key, timeout, outage or refused request."""
