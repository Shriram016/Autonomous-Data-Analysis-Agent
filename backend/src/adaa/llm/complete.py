"""llm.complete: the one door for every LLM call (ADR 0009).

All app code calls complete(job, messages, form) and gets back a filled, checked form,
or a clear error. It never returns free text. The reply is checked with Pydantic even
though strict mode already forces the JSON shape: the form has rules a JSON schema can't
fully express (the model validators in StructuredRequest, for example). A reply that
fails the check gets ONE retry with the errors; a second failure raises LlmOutputError.

Every call writes one usage log line (logger "adaa.llm"), failures included. The line
holds names and counts only, never the prompt or reply text: they can hold personal
data and masking is not built yet. The durable record (a database row per question)
comes with the conversation tables in M1.4 / M1.5.

Not here yet (later slices, same function): masking, fallback model, retry on 429/503,
circuit breaker, rate limiter.
"""

import logging
import time
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from adaa.llm.adapters.base import Adapter, Message
from adaa.llm.config import JobSettings, LlmConfig, get_config
from adaa.llm.types import (
    AdapterReply,
    LlmOutputError,
    LlmResult,
    LlmUnavailableError,
    Usage,
)

log = logging.getLogger("adaa.llm")

Outcome = Literal["ok", "output_error", "unavailable"]

RETRY_PROMPT = (
    "Your reply did not match the required form. Errors:\n{errors}\n"
    "Reply again with valid JSON only, matching the schema."
)

NO_USAGE = Usage(input_tokens=0, output_tokens=0, thinking_tokens=0, cost_usd=0.0)


def adapter_for(job: JobSettings) -> Adapter:
    """The real adapter the config names. The anthropic adapter arrives in step 6."""
    raise LlmUnavailableError(f"The '{job.provider.adapter}' adapter is not built yet.")


def total_usage(replies: list[AdapterReply]) -> Usage:
    """Usage of every attempt added together: the retry's cost is never hidden."""
    return sum((r.usage for r in replies), NO_USAGE)


def log_call(
    job: JobSettings, outcome: Outcome, replies: list[AdapterReply], started: float
) -> None:
    usage = total_usage(replies)
    fields: dict[str, Any] = {
        "job": job.job,
        "model": job.model_name,
        "outcome": outcome,
        "attempts": len(replies),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "thinking_tokens": usage.thinking_tokens,
        "cost_usd": round(usage.cost_usd, 6),
        "seconds": round(time.monotonic() - started, 3),
    }
    text = " ".join(f"{k}={v}" for k, v in fields.items())
    log.info("llm_call %s", text, extra={"llm": fields})


def ask_with_one_retry[Form: BaseModel](
    adapter: Adapter,
    messages: list[Message],
    form: type[Form],
    job: JobSettings,
    replies: list[AdapterReply],  # each reply is appended here, for usage and the log
) -> Form:
    schema = form.model_json_schema()
    # An LlmUnavailableError from send() passes straight up: no retry here (later slice).
    replies.append(adapter.send(messages, schema, job))
    try:
        return form.model_validate_json(replies[-1].text)
    except ValidationError as first_error:
        retry = [
            *messages,
            Message(role="assistant", content=replies[-1].text),
            Message(role="user", content=RETRY_PROMPT.format(errors=first_error)),
        ]
    replies.append(adapter.send(retry, schema, job))
    try:
        return form.model_validate_json(replies[-1].text)
    except ValidationError as e:
        raise LlmOutputError("The AI reply did not match the expected form after 2 tries.") from e


def complete[Form: BaseModel](
    job: str,
    messages: list[Message],
    form: type[Form],
    *,
    adapter: Adapter | None = None,  # tests pass the fake adapter here
    config: LlmConfig | None = None,
) -> LlmResult[Form]:
    started = time.monotonic()
    settings = (config or get_config()).job_settings(job)
    adapter = adapter or adapter_for(settings)

    replies: list[AdapterReply] = []
    try:
        output = ask_with_one_retry(adapter, messages, form, settings, replies)
    except LlmOutputError:
        log_call(settings, "output_error", replies, started)
        raise
    except LlmUnavailableError:
        log_call(settings, "unavailable", replies, started)
        raise
    log_call(settings, "ok", replies, started)

    return LlmResult[Form](
        output=output,
        usage=total_usage(replies),
        attempts=len(replies),
        model_name=settings.model_name,
        seconds=time.monotonic() - started,
    )
