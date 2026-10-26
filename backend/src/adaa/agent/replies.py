"""The quick-route replies: clarify, refuse, metadata, off_topic (§0 M2 step 2c).

After the router picks a quick route, ONE reply step runs (no form for the numbers route,
no SQL):

    clarify   → LLM fills ClarifyForm  → its message + 2–3 options as suggestion buttons
    refuse    → LLM fills RefuseForm   → the missing data + 1 suggestion button
    metadata  → LLM fills MetadataForm → only the TOPIC; code writes the reply from the
                semantic layer, so the facts are never the LLM's
    off_topic → no LLM: a fixed text + 3 example buttons picked at random from 6

Each route has its own prompt (prompts/clarify.md, refuse.md, metadata.md) and its own
form, run by the one `reply` job (config/llm.yaml). The LLM writes the suggestions as text
from the metric list in its prompt; they are not checked before they are shown (§0 2c
decision 2). Any LLM failure → a code-made fallback reply at once (max_attempts 1) and one
`reply_failed` log line. Every reply writes one `quick_reply` line (names only), so
refusals and fallbacks can be counted.
"""

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from adaa.agent.prompts import Prompt, dimension_lines, load_prompt, metric_lines
from adaa.llm.adapters.base import Adapter, Message
from adaa.llm.complete import NO_USAGE, complete
from adaa.llm.types import LlmError, Usage
from adaa.semantic_layer.definitions import SemanticLayer

log = logging.getLogger("adaa.agent")

QuickRoute = Literal["clarify", "refuse", "metadata", "off_topic"]

# Off-topic examples: one per main kind of question, each covered by the eval (2d).
EXAMPLES = [
    "Revenue by month in 2017",
    "Top 5 product categories by revenue",
    "Late delivery rate 2018 vs 2017",
    "What is the cancellation rate?",
    "Average review score by customer state",
    "Orders per quarter in 2017",
]
EXAMPLES_SHOWN = 3

# ---------- the three forms the LLM fills ----------


class ClarifyForm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)  # what is unclear: "Best by what? Pick one:"
    options: list[str] = Field(min_length=2, max_length=3)  # full questions


class RefuseForm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_data: str = Field(min_length=1)  # "The data has no product costs, so …"
    suggestion: str = Field(min_length=1)  # the closest question the data can answer


class MetadataForm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: Literal["data_overview", "date_range", "definition"]
    metric: str | None = None  # definition only: a metric name, or the user's own word


# ---------- prompts, built once (like the agent prompt) ----------


@dataclass(frozen=True)
class ReplyPrompts:
    clarify: Prompt
    refuse: Prompt
    metadata: Prompt


@dataclass(frozen=True)
class DataFacts:
    """What the code-written replies say about the data."""

    first_month: date
    last_month: date
    data_date: date  # the last full month's end: the agent's "today"


def data_range(facts: DataFacts) -> str:
    return f"orders from {facts.first_month:%Y-%m} to {facts.data_date.isoformat()}"


def build_reply_prompts(layer: SemanticLayer, facts: DataFacts) -> ReplyPrompts:
    shared = {
        "data_range": data_range(facts),
        "metrics": metric_lines(layer),
        "dimensions": dimension_lines(layer),
    }
    return ReplyPrompts(
        clarify=load_prompt("clarify", shared),
        refuse=load_prompt("refuse", shared),
        metadata=load_prompt("metadata", {"metric_names": ", ".join(layer.metrics)}),
    )


# ---------- replies written by code ----------


def overview_text(layer: SemanticLayer, facts: DataFacts) -> str:
    metrics = ", ".join(m.label for m in layer.metrics.values())
    dimensions = ", ".join(d.label for d in layer.dimensions.values())
    return (
        f"I answer questions about the store's {data_range(facts)}. "
        f"Metrics: {metrics}. Breakdowns: {dimensions}."
    )


def date_range_text(facts: DataFacts) -> str:
    return (
        f"The data has orders from {facts.first_month:%Y-%m} to {facts.last_month:%Y-%m}. "
        f"Complete months end on {facts.data_date.isoformat()}: I use that day as 'today' "
        "for questions like 'last month'."
    )


STATUS_TEXT = {
    "default": "Delivered orders only, unless you ask for an order status.",
    "built_in": "Delivered orders only.",
    "all": "Orders in every status.",
}


def definition_text(metric_name: str | None, layer: SemanticLayer, facts: DataFacts) -> str:
    metric = layer.metrics.get(metric_name or "")
    if metric is None:
        unknown = f"I have no metric called {metric_name}. " if metric_name else ""
        return unknown + overview_text(layer, facts)
    status = f" {STATUS_TEXT[metric.status]}" if metric.status else ""
    return f"{metric.label}: {metric.description}{status}"


def metadata_text(form: MetadataForm, layer: SemanticLayer, facts: DataFacts) -> str:
    match form.topic:
        case "data_overview":
            return overview_text(layer, facts)
        case "date_range":
            return date_range_text(facts)
        case "definition":
            return definition_text(form.metric, layer, facts)


OFF_TOPIC_TEXT = (
    "I can only answer questions about the store's data: orders, revenue, deliveries, "
    "customers and reviews. For example:"
)
CLARIFY_FALLBACK = (
    "Your question can mean several things. Please ask it more exactly, for example by "
    "naming a metric such as revenue, orders or review score."
)
REFUSE_FALLBACK = "The store's data can't answer that question. For example, you can ask:"


# ---------- the one function the reply node calls ----------


class QuickReply(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    suggestions: list[str] = []  # full questions, shown as buttons
    usage: Usage = NO_USAGE
    used_fallback: bool = False  # the LLM failed; the text is code-made


Pick = Callable[[list[str], int], list[str]]  # random.sample; tests pass a fixed pick


def make_reply(
    route: QuickRoute,
    question: str,
    prompts: ReplyPrompts,
    layer: SemanticLayer,
    facts: DataFacts,
    adapter: Adapter | None = None,
    pick: Pick = random.sample,
) -> QuickReply:
    if route == "off_topic":
        reply = QuickReply(text=OFF_TOPIC_TEXT, suggestions=pick(EXAMPLES, EXAMPLES_SHOWN))
    else:
        reply = ask_llm(route, question, prompts, layer, facts, adapter, pick)
    log.info("quick_reply route=%s used_fallback=%s", route, reply.used_fallback)
    return reply


def ask_llm(
    route: Literal["clarify", "refuse", "metadata"],
    question: str,
    prompts: ReplyPrompts,
    layer: SemanticLayer,
    facts: DataFacts,
    adapter: Adapter | None,
    pick: Pick,
) -> QuickReply:
    choices: dict[str, tuple[Prompt, type[BaseModel]]] = {
        "clarify": (prompts.clarify, ClarifyForm),
        "refuse": (prompts.refuse, RefuseForm),
        "metadata": (prompts.metadata, MetadataForm),
    }
    prompt, form = choices[route]
    messages = [
        Message(role="system", content=prompt.text),
        Message(role="user", content=question),
    ]
    try:
        result = complete("reply", messages, form, adapter=adapter)
    except LlmError as e:
        log.warning("reply_failed route=%s reason=%s", route, type(e).__name__)
        return fallback(route, layer, facts, pick)

    out = result.output
    if isinstance(out, ClarifyForm):
        return QuickReply(text=out.message, suggestions=out.options, usage=result.usage)
    if isinstance(out, RefuseForm):
        return QuickReply(text=out.missing_data, suggestions=[out.suggestion], usage=result.usage)
    assert isinstance(out, MetadataForm)
    return QuickReply(text=metadata_text(out, layer, facts), usage=result.usage)


def fallback(route: str, layer: SemanticLayer, facts: DataFacts, pick: Pick) -> QuickReply:
    """The code-made reply when the LLM fails: plain, but always correct."""
    if route == "clarify":
        return QuickReply(text=CLARIFY_FALLBACK, used_fallback=True)
    if route == "refuse":
        return QuickReply(
            text=REFUSE_FALLBACK, suggestions=pick(EXAMPLES, EXAMPLES_SHOWN), used_fallback=True
        )
    return QuickReply(text=overview_text(layer, facts), used_fallback=True)  # metadata
