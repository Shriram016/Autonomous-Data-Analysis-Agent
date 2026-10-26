"""The router: which route does a question take? (§0 M2 step 2, View 3 routes 1 and 4–7).

    question → router → numbers   (the M1 flow: understand → query → answer)
                      → clarify   (ask back with 2–3 options)
                      → refuse    (name the missing data, offer the closest question)
                      → off_topic (decline, say what the assistant can do)
                      → metadata  (answer from the semantic layer, no SQL)

The router tries the jobs in config/llm.yaml `router.order`, first = primary: Jev
(a classifier with a confidence score), then Haiku. A failed option writes one
`router_fallback` log line and the next one is tried; when every option fails it writes
`router_failed` and the question goes to the numbers route, today's behaviour. The log
lines hold names and counts only, never the question (they join the M6 monitoring).

Whatever answers, the result has one shape, RouteDecision, so the rest of the agent never
knows which model routed. The route descriptions are written once (ROUTES) and sent to
both models: Jev as its choice criteria, Haiku inside its prompt (prompts/router.md).
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from adaa.agent.prompts import Prompt, load_prompt
from adaa.llm.adapters.base import Adapter, Message
from adaa.llm.adapters.jev_adapter import JevAdapter
from adaa.llm.complete import NO_USAGE, Outcome, complete, log_call
from adaa.llm.config import JobSettings, LlmConfig, get_config
from adaa.llm.types import LlmError, LlmOutputError, LlmUnavailableError, Usage
from adaa.semantic_layer.definitions import SemanticLayer

log = logging.getLogger("adaa.agent")

Route = Literal["numbers", "clarify", "refuse", "off_topic", "metadata"]
DEFAULT_ROUTE: Route = "numbers"  # every option failed: the M1 behaviour

ROUTES: dict[str, str] = {
    "numbers": (
        "A business question the store's data can answer with a number or a table: one of "
        "the metrics, maybe broken down, filtered, sorted or compared between periods."
    ),
    "clarify": (
        "A question about the store's data that is too vague to answer: a key word has "
        "several meanings (best products: by revenue, by orders or by rating?) and the "
        "data has no written meaning for it."
    ),
    "refuse": (
        "A business question that needs data the store does not have, such as profit, "
        "costs, stock, marketing, website visits or anything after the data ends."
    ),
    "off_topic": (
        "Not about the store's business data: small talk, jokes, coding, general knowledge."
    ),
    "metadata": (
        "A question about the assistant itself: which data or metrics it has, the date "
        "range, or how a metric is defined."
    ),
}


class RouteForm(BaseModel):
    """What Haiku fills: one field."""

    model_config = ConfigDict(extra="forbid")

    route: Route


class RouteDecision(BaseModel):
    """The router's answer, the same shape whichever model gave it."""

    model_config = ConfigDict(frozen=True)

    route: Route
    confidence: float | None = Field(default=None, ge=0, le=1)  # Jev only; None from Haiku
    source: str  # the job that answered (route_jev, route_haiku), or "default"
    usage: Usage = NO_USAGE


@dataclass(frozen=True)
class RouterTexts:
    """Both models' instructions, built once from the semantic layer (like the prompts)."""

    prompt: Prompt  # Haiku's system prompt: prompts/router.md, filled
    instructions: str  # Jev's instructions for its one choice question


def build_router_texts(layer: SemanticLayer, data_date: date) -> RouterTexts:
    data_range = f"orders from 2016 to {data_date.isoformat()}"
    metrics = ", ".join(f"{name} ({', '.join(m.terms)})" for name, m in layer.metrics.items())
    dimensions = ", ".join(layer.dimensions)
    defaults = ", ".join(term for d in layer.defaults.values() for term in d.terms)
    values = {
        "routes": "\n".join(f"- `{name}`: {text}" for name, text in ROUTES.items()),
        "metrics": metrics,
        "dimensions": dimensions,
        "defaults": defaults,
        "data_range": data_range,
    }
    instructions = (
        "Pick the route for a question sent to a data assistant for a Brazilian online store "
        f"({data_range}). The data has these metrics: {metrics}. Breakdowns: {dimensions}. "
        f"Vague words with a written meaning are numbers questions: {defaults}."
    )
    return RouterTexts(prompt=load_prompt("router", values), instructions=instructions)


def ask_jev(question: str, job: JobSettings, texts: RouterTexts, jev: JevAdapter) -> RouteDecision:
    started = time.monotonic()
    try:
        reply = jev.choose(question, texts.instructions, ROUTES, job)
        data = json.loads(reply.text)
        decision = RouteDecision(
            route=data["choice"], confidence=data["confidence"], source=job.job, usage=reply.usage
        )
    except LlmError as e:
        outcome: Outcome = "unavailable" if isinstance(e, LlmUnavailableError) else "output_error"
        log_call(job, outcome, [], started)
        raise
    except ValidationError as e:  # e.g. a confidence outside 0–1
        log_call(job, "output_error", [reply], started)
        raise LlmOutputError("The classifier reply did not have the expected values.") from e
    log_call(job, "ok", [reply], started)
    return decision


def ask_chat_model(
    question: str, job: JobSettings, texts: RouterTexts, adapter: Adapter | None
) -> RouteDecision:
    messages = [
        Message(role="system", content=texts.prompt.text),
        Message(role="user", content=question),
    ]
    reply = complete(job.job, messages, RouteForm, adapter=adapter)  # logs its own line
    return RouteDecision(route=reply.output.route, source=job.job, usage=reply.usage)


def route_question(
    question: str,
    texts: RouterTexts,
    *,
    config: LlmConfig | None = None,
    adapter: Adapter | None = None,  # tests: the fake chat model
    jev: JevAdapter | None = None,  # tests: a Jev adapter with a mock HTTP client
) -> RouteDecision:
    config = config or get_config()
    order = config.router.order
    for position, name in enumerate(order):
        job = config.job_settings(name)
        try:
            if job.provider.adapter == "jev":
                return ask_jev(question, job, texts, jev or JevAdapter())
            return ask_chat_model(question, job, texts, adapter)
        except LlmError as e:
            if position + 1 < len(order):
                log.warning(
                    "router_fallback from=%s to=%s reason=%s",
                    name,
                    order[position + 1],
                    type(e).__name__,
                )
    log.warning("router_failed tried=%d route=%s", len(order), DEFAULT_ROUTE)
    return RouteDecision(route=DEFAULT_ROUTE, source="default")
