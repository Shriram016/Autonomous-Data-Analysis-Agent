"""The Anthropic adapter: sends one request to Claude through the official SDK (ADR 0009).

This is the only file that imports the `anthropic` package. It turns our request into the
SDK's request (system prompt split out, schema cleaned for strict mode, thinking set from
config), sends it, and turns the reply and any SDK error into our shapes. It does NOT
check the reply against the form; llm.complete does that.

The SDK retries 429, 5xx and timeouts by itself (2 retries). We keep that until our own
retry rules exist (§0 failure handling); then set max_retries=0 so the two don't stack.
"""

import os
import time
from dataclasses import dataclass
from typing import Any

import anthropic
from dotenv import dotenv_values

from adaa.llm.adapters.base import Message
from adaa.llm.config import JobSettings
from adaa.llm.types import AdapterReply, LlmOutputError, LlmUnavailableError, make_usage
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

    def send(
        self, messages: list[Message], schema: dict[str, Any], job: JobSettings
    ) -> AdapterReply:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        thinking = thinking_params(job)
        output_config: dict[str, Any] = {
            "format": {"type": "json_schema", "schema": clean_schema(schema)}
        }
        if "effort" in thinking:
            output_config["effort"] = thinking.pop("effort")

        assert job.settings.max_tokens, "config.check() requires max_tokens for anthropic jobs"
        started = time.monotonic()
        try:
            response = self.get_client(job).messages.create(
                model=job.model_name,
                max_tokens=job.settings.max_tokens,
                messages=turns,
                output_config=output_config,
                timeout=float(job.settings.timeout_seconds),
                **({"system": system} if system else {}),
                **thinking,
            )
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
        seconds = time.monotonic() - started

        if response.stop_reason == "refusal":
            raise LlmOutputError("The AI declined to answer this request.")
        if response.stop_reason == "max_tokens":
            raise LlmOutputError("The AI reply was cut off; increase max_tokens for this job.")

        text = next((b.text for b in response.content if b.type == "text"), "")
        details = response.usage.output_tokens_details
        usage = make_usage(
            response.usage.input_tokens,
            response.usage.output_tokens,
            details.thinking_tokens if details and details.thinking_tokens else 0,
            job.model.price_per_million,
        )
        return AdapterReply(text=text, usage=usage, seconds=seconds)
