"""The Jev adapter: asks TypeSafe's Jev classifier to pick one choice (§0 M2 step 2, router).

Jev is not a chat model: it gets a `state` (our text) and typed questions, and answers a
"choice" question with the chosen option, the probabilities and a confidence. So it does
not use the Adapter protocol (messages in, form text out) and llm.complete never calls it;
the router does (agent/router.py). It still returns an AdapterReply, so usage and the
llm_call log line work the same as for every other model.

Reached through OpenRouter's decisions API, which is ALPHA (confirmed 2026-10-26 from
OpenRouter's page): the request format can change between releases, so this is the only
file that knows it. Errors become our two error types, like the Anthropic adapter.

Untested against the real API until OPENROUTER_API_KEY is in .env (§0 M2 step 2).
"""

import json
import time
from dataclasses import dataclass, field

import httpx

from adaa.llm.adapters.anthropic_adapter import read_secret
from adaa.llm.config import JobSettings
from adaa.llm.types import AdapterReply, LlmOutputError, LlmUnavailableError, make_usage

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
QUESTION_ID = "choice"  # Jev never sees the ID; the meaning is in the instructions


class MissingKeyError(LlmUnavailableError):
    """The API key is not in .env: fail at once, with no network call."""


@dataclass
class JevAdapter:
    client: httpx.Client = field(default_factory=httpx.Client)  # tests pass a mock client

    def choose(
        self, state: str, instructions: str, criteria: dict[str, str], job: JobSettings
    ) -> AdapterReply:
        """Pick one key of `criteria` (option → description) for `state`.

        The reply text is JSON: {"choice": "<option>", "confidence": 0.0–1.0}.
        """
        key = read_secret(job.provider.api_key_env)
        if not key:
            raise MissingKeyError(f"{job.provider.api_key_env} is not set in .env.")
        body = {
            "model": job.model_name,
            "state": state,
            "questions": {
                QUESTION_ID: {"type": "choice", "instructions": instructions, "criteria": criteria}
            },
        }
        started = time.monotonic()
        try:
            response = self.client.post(
                ENDPOINT,
                json=body,
                headers={"Authorization": f"Bearer {key}"},
                timeout=float(job.settings.timeout_seconds),
            )
        except httpx.TimeoutException as e:
            raise LlmUnavailableError("The classifier took too long to answer.") from e
        except httpx.HTTPError as e:
            raise LlmUnavailableError("The classifier could not be reached.") from e
        seconds = time.monotonic() - started
        if response.status_code != 200:  # 401 key, 429 busy, 5xx outage, 400 format change
            raise LlmUnavailableError(f"The classifier returned an error ({response.status_code}).")

        try:
            data = response.json()
            answer = data["answers"][QUESTION_ID]
            choice, confidence = answer["choice"], answer.get("confidence")
            usage = data.get("usage", {})
            input_tokens, output_tokens = (
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            )
        except (ValueError, KeyError, TypeError) as e:  # not JSON, or not the documented shape
            raise LlmOutputError("The classifier reply did not have the expected shape.") from e
        if choice not in criteria:
            raise LlmOutputError("The classifier picked an option that was not offered.")
        return AdapterReply(
            text=json.dumps({"choice": choice, "confidence": confidence}),
            usage=make_usage(input_tokens, output_tokens, 0, job.model.price_per_million),
            seconds=seconds,
        )
