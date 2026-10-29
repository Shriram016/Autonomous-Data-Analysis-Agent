"""The Anthropic adapter: sends one request to Claude through the official SDK (ADR 0009).

This is the only file that imports the `anthropic` package. It turns our request into the
SDK's request (system prompt split out and marked for caching, schema cleaned for strict
mode, thinking set from config), sends it, and turns the reply and any SDK error into our
shapes. It does NOT check the reply against the form; llm.complete does that.

Prompt caching (M2 step 4): the system prompt is the same for every question, so it ends
with a cache mark; the question and data rows come after it, in the user message.

The SDK retries 429, 5xx and timeouts by itself (2 retries). We keep that until our own
retry rules exist (§0 failure handling); then set max_retries=0 so the two don't stack.
"""

import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import anthropic
from dotenv import dotenv_values

from adaa.llm.adapters.base import Message
from adaa.llm.config import JobSettings
from adaa.llm.types import AdapterReply, LlmOutputError, LlmUnavailableError, Usage, make_usage
from adaa.settings import REPO_ROOT

SDK_MAX_RETRIES = 2  # set to 0 when our own retry rules arrive

# JSON-schema rules that strict mode does not accept. They are removed from the copy we
# send; Pydantic still checks every one of them on the reply in llm.complete.
UNSUPPORTED = frozenset(
    {
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
    }
)


def read_secret(name: str) -> str | None:
    """A secret from the environment, else from the repo-root .env. Never logged."""
    return os.environ.get(name) or dotenv_values(REPO_ROOT / ".env").get(name) or None


def clean_schema(node: Any) -> Any:
    """A copy of the schema without the rules strict mode does not accept.

    Property NAMES are kept even if they match a rule name (a field called "minimum").
    Every object gets additionalProperties: false, which strict mode requires.
    """
    if isinstance(node, list):
        return [clean_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key in UNSUPPORTED:
            continue
        if key in ("properties", "$defs"):  # a map of names → schemas: keep every name
            cleaned[key] = {name: clean_schema(sub) for name, sub in value.items()}
        else:
            cleaned[key] = clean_schema(value)
    if cleaned.get("type") == "object":
        cleaned["additionalProperties"] = False
    return cleaned


def thinking_params(job: JobSettings) -> dict[str, Any]:
    level = job.settings.thinking
    if level == "disabled":
        return {"thinking": {"type": "disabled"}}
    return {"thinking": {"type": "adaptive"}, "effort": level}


def system_param(system: str, job: JobSettings) -> str | list[dict[str, Any]]:
    """The system prompt, as one block with a cache mark when the job caches.

    The mark caches everything up to and including this block. "ephemeral" alone means
    5 minutes; "1h" must be asked for.
    """
    cache = job.settings.cache
    if cache == "none":
        return system
    mark: dict[str, Any] = {"type": "ephemeral"}
    if cache == "1h":
        mark["ttl"] = "1h"
    return [{"type": "text", "text": system, "cache_control": mark}]


def request_params(
    messages: list[Message], schema: dict[str, Any], job: JobSettings
) -> dict[str, Any]:
    """The SDK request for one call. A normal call and a batch request both use it, so the
    two can never differ."""
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    turns = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    thinking = thinking_params(job)
    output_config: dict[str, Any] = {
        "format": {"type": "json_schema", "schema": clean_schema(schema)}
    }
    if "effort" in thinking:
        output_config["effort"] = thinking.pop("effort")
    assert job.settings.max_tokens, "config.check() requires max_tokens for anthropic jobs"
    return {
        "model": job.model_name,
        "max_tokens": job.settings.max_tokens,
        "messages": turns,
        "output_config": output_config,
        **({"system": system_param(system, job)} if system else {}),
        **thinking,
    }


@contextmanager
def sdk_errors() -> Generator[None]:
    """Turn an SDK error into our LlmUnavailableError with a plain message."""
    try:
        yield
    except anthropic.APITimeoutError as e:
        raise LlmUnavailableError("The AI service took too long to answer.") from e
    except anthropic.APIConnectionError as e:
        raise LlmUnavailableError("The AI service could not be reached.") from e
    except anthropic.AuthenticationError as e:
        raise LlmUnavailableError("The AI service refused the API key.") from e
    except anthropic.RateLimitError as e:
        raise LlmUnavailableError("The AI service is busy (rate limit).") from e
    except anthropic.APIStatusError as e:  # 5xx outage, or a 400 from a bad request
        raise LlmUnavailableError(f"The AI service returned an error ({e.status_code}).") from e


BATCH_PRICE = 0.5  # a batch request costs half the normal price


@dataclass(frozen=True)
class BatchAnswer:
    custom_id: str
    text: str | None  # the raw reply (should be JSON); None when the request failed
    error: str | None
    usage: Usage | None


def read_reply(response: Any, job: JobSettings) -> tuple[str, Usage]:
    """The text and the counts of one SDK message: a normal reply or a batch answer."""
    if response.stop_reason == "refusal":
        raise LlmOutputError("The AI declined to answer this request.")
    if response.stop_reason == "max_tokens":
        raise LlmOutputError("The AI reply was cut off; increase max_tokens for this job.")

    text = next((b.text for b in response.content if b.type == "text"), "")
    counts = response.usage
    details = getattr(counts, "output_tokens_details", None)
    usage = make_usage(
        counts.input_tokens,  # the uncached part only
        counts.output_tokens,
        details.thinking_tokens if details and details.thinking_tokens else 0,
        job.model.price_per_million,
        # None (not 0) when the request had no cache mark
        cache_write_tokens=getattr(counts, "cache_creation_input_tokens", None) or 0,
        cache_read_tokens=getattr(counts, "cache_read_input_tokens", None) or 0,
        cache=job.settings.cache,
    )
    return text, usage


@dataclass
class AnthropicAdapter:
    client: Any = None  # tests pass a fake client; otherwise made on first use

    def get_client(self, job: JobSettings) -> Any:
        if self.client is None:
            key = read_secret(job.provider.api_key_env)
            if not key:
                raise LlmUnavailableError(f"{job.provider.api_key_env} is not set in .env.")
            self.client = anthropic.Anthropic(api_key=key, max_retries=SDK_MAX_RETRIES)
        return self.client

    def create_batch(
        self,
        requests: list[tuple[str, list[Message]]],  # (custom_id, messages) per request
        schema: dict[str, Any],
        job: JobSettings,
    ) -> str:
        """Send many requests as one Message Batch (half price, answers within 24 h).

        Returns the batch ID. Nothing is checked here: the answers are read later.
        """
        batch_requests = [
            {"custom_id": custom_id, "params": request_params(messages, schema, job)}
            for custom_id, messages in requests
        ]
        with sdk_errors():
            batch = self.get_client(job).messages.batches.create(requests=batch_requests)
        return str(batch.id)

    def send(
        self, messages: list[Message], schema: dict[str, Any], job: JobSettings
    ) -> AdapterReply:
        started = time.monotonic()
        with sdk_errors():
            response = self.get_client(job).messages.create(
                **request_params(messages, schema, job),
                timeout=float(job.settings.timeout_seconds),
            )
        seconds = time.monotonic() - started
        text, usage = read_reply(response, job)
        return AdapterReply(text=text, usage=usage, seconds=seconds)

    def batch_status(self, batch_id: str, job: JobSettings) -> str:
        """'in_progress', 'canceling' or 'ended' (every answer is ready, or expired)."""
        with sdk_errors():
            batch = self.get_client(job).messages.batches.retrieve(batch_id)
        return str(batch.processing_status)

    def batch_answers(self, batch_id: str, job: JobSettings) -> list[BatchAnswer]:
        """Every answer of an ended batch. A failed request is an answer with an error."""
        with sdk_errors():
            entries = list(self.get_client(job).messages.batches.results(batch_id))
        answers = []
        for entry in entries:
            result = entry.result
            if result.type != "succeeded":  # errored, canceled or expired: no message
                answers.append(BatchAnswer(entry.custom_id, None, f"request {result.type}", None))
                continue
            try:
                text, usage = read_reply(result.message, job)
            except LlmOutputError as e:  # refused or cut off: the tokens were still billed
                answers.append(BatchAnswer(entry.custom_id, None, str(e), None))
                continue
            half = usage.model_copy(update={"cost_usd": usage.cost_usd * BATCH_PRICE})
            answers.append(BatchAnswer(entry.custom_id, text, None, half))
        return answers
