"""Shapes that all the LLM code shares (ADR 0009).

Every adapter (fake, anthropic, later openai_compatible) returns an AdapterReply, so
llm.complete never cares which provider answered. llm.complete returns an LlmResult to
the rest of the app. Token counts are always stored, so the cost can be recomputed if a
price in config/llm.yaml was stale (§0, Cost).
"""

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from adaa.llm.config import Cache, Price


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Input tokens at the full price. With prompt caching the provider counts the cached
    # part apart, so the whole prompt = input + cache_write + cache_read (M2 step 4).
    input_tokens: NonNegativeInt
    # All billed output tokens. Thinking tokens are INCLUDED here, not added on top:
    # the provider bills them as output and counts them inside output_tokens.
    output_tokens: NonNegativeInt
    thinking_tokens: NonNegativeInt = 0  # the part of output_tokens spent thinking
    cache_write_tokens: NonNegativeInt = 0  # prompt stored in the cache by this call
    cache_read_tokens: NonNegativeInt = 0  # prompt reused from the cache by this call
    cost_usd: NonNegativeFloat

    def __add__(self, other: "Usage") -> "Usage":
        """Usage of two attempts together (the first try + the retry)."""
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            thinking_tokens=self.thinking_tokens + other.thinking_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


def cost_usd(
    input_tokens: int,
    output_tokens: int,
    price: Price,
    *,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache: Cache = "5m",
) -> float:
    """Cost of one call. output_tokens already includes the thinking tokens.

    `cache` is the job's cache time; it picks the write price (5 minutes or 1 hour).
    """
    total = input_tokens * price.input + output_tokens * price.output
    if cache_write_tokens or cache_read_tokens:
        write_price = price.cache_write_1h if cache == "1h" else price.cache_write_5m
        if write_price is None or price.cache_read is None:  # config.check() prevents this
            raise ValueError("Cache tokens were billed, but the model has no cache prices.")
        total += cache_write_tokens * write_price + cache_read_tokens * price.cache_read
    return total / 1_000_000


def make_usage(
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int,
    price: Price,
    *,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache: Cache = "5m",
) -> Usage:
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        cache_write_tokens=cache_write_tokens,
        cache_read_tokens=cache_read_tokens,
        cost_usd=cost_usd(
            input_tokens,
            output_tokens,
            price,
            cache_write_tokens=cache_write_tokens,
            cache_read_tokens=cache_read_tokens,
            cache=cache,
        ),
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
