"""The nodes of the agent graph: route, then understand → query → answer, or reply
(§0 M1.3 step 6; route and reply: M2 step 2).

Each node takes the state and the context and returns ONLY the fields it fills; the graph
merges them into the state. A node that fails returns an `error` (a kind + a plain message)
and the graph stops. The nodes add no new checks: they run the existing ones in order.
"""

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from adaa.agent.context import AgentContext
from adaa.agent.facts import build_facts
from adaa.agent.replies import make_reply
from adaa.agent.state import AgentError, AgentState
from adaa.agent.values import ValueNotFoundError, check_filters
from adaa.guardrails.numbers import unknown_numbers
from adaa.llm.adapters.base import Message
from adaa.llm.complete import complete
from adaa.llm.config import get_config
from adaa.llm.types import LlmError, LlmOutputError, LlmUnavailableError
from adaa.semantic_layer.compiler import CompileError
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import DataUnavailableError, QueryTimeoutError

log = logging.getLogger("adaa.agent")

NOT_UNDERSTOOD = "I could not turn the question into a request. Please rephrase it."
DEFAULT_MAX_ROWS = 20


class AnswerForm(BaseModel):
    """What the answer LLM fills: the answer is a field, never free text (ADR 0009)."""

    model_config = ConfigDict(extra="forbid")

    answer_text: str = Field(min_length=1)


def route(state: AgentState, context: AgentContext) -> dict[str, Any]:
    """Question → route (agent/router.py). Never stops the graph: when every router option
    fails, the router itself answers `numbers`, the M1 behaviour."""
    decision = context.route(state.question)
    return {"route": decision, "usage": state.usage + decision.usage}


def reply(state: AgentState, context: AgentContext) -> dict[str, Any]:
    """A quick route's reply (agent/replies.py): no form, no SQL. Never stops the graph:
    when the LLM fails, a code-made fallback reply is used."""
    assert state.route is not None and state.route.route != "numbers"
    result = make_reply(
        state.route.route,
        state.question,
        context.reply_prompts,
        context.layer,
        context.data_facts,
        adapter=context.adapter,
    )
    return {
        "answer_text": result.text,
        "suggestions": result.suggestions,
        "usage": state.usage + result.usage,
    }


def understand(state: AgentState, context: AgentContext) -> dict[str, Any]:
    """Question → checked form.

    Check 1 (the form's shape, with one retry) runs inside complete(); check 2 (every filter
    value is real) runs here. Check 3 (names and rules) is the compiler, in the query node.
    """
    messages = [
        Message(role="system", content=context.agent_prompt.text),
        Message(role="user", content=state.question),
    ]
    try:
        reply = complete("agent", messages, StructuredRequest, adapter=context.adapter)
    except LlmUnavailableError as e:
        return {"error": AgentError(kind="llm_unavailable", message=str(e))}
    except LlmOutputError:
        return {"error": AgentError(kind="llm_output", message=NOT_UNDERSTOOD)}
    # A failed call's cost is in the usage log line, not here: complete() raises instead
    # of returning it. Only successful calls add to the state's usage for now.
    usage = state.usage + reply.usage
    try:
        form, notes = check_filters(reply.output, context.catalogue)
    except ValueNotFoundError as e:
        return {"usage": usage, "error": AgentError(kind="value_not_found", message=str(e))}
    return {"form": form, "value_notes": notes, "usage": usage}


def query(state: AgentState, context: AgentContext) -> dict[str, Any]:
    """Checked form → rows, through the M1.1 path (compiler, then the runner as adaa_query).

    Check 3 runs here: the compiler refuses names that don't exist, a double count, or a
    status split on a delivery metric. Every error already has a plain M1.1 message.
    """
    assert state.form is not None, "query runs only after understand filled the form"
    try:
        return {"result": context.ask(state.form)}
    except CompileError as e:
        return {"error": AgentError(kind="compile_refused", message=str(e))}
    except QueryTimeoutError as e:
        return {"error": AgentError(kind="query_timeout", message=str(e))}
    except DataUnavailableError as e:
        return {"error": AgentError(kind="data_unavailable", message=str(e))}


def answer(state: AgentState, context: AgentContext) -> dict[str, Any]:
    """Rows → answer text. Never stops the graph: the template answer is the fallback.

    The answer job has max_attempts 1, so any failure — the LLM is down, its form is bad,
    or a number in its text is not in the data — means the template answer at once (no
    second paid call), and one log line so the failures of this component can be counted.
    """
    assert state.form is not None and state.result is not None, "answer runs after query"
    max_rows = get_config().job_settings("answer").settings.max_rows or DEFAULT_MAX_ROWS
    facts = build_facts(state.result, state.form, context.layer, max_rows)
    messages = [
        Message(role="system", content=context.answer_prompt.text),
        Message(role="user", content=f"Question: {state.question}\n\n{facts.result_text()}"),
    ]
    fallback = {"facts": facts, "answer_text": facts.template_answer, "used_template": True}
    try:
        reply = complete("answer", messages, AnswerForm, adapter=context.adapter)
    except LlmError as e:
        log.warning("answer_llm_failed reason=%s", type(e).__name__)
        return fallback

    usage = state.usage + reply.usage
    periods = [p for p in (state.form.period, state.form.compare_to) if p]
    period = [str(day) for p in periods for day in (p.start, p.end)]
    allowed = [*facts.allowed_numbers, state.question, *period]
    bad = unknown_numbers(reply.output.answer_text, allowed)
    if bad:
        log.warning("answer_guardrail_failed bad_numbers=%d", len(bad))
        return {**fallback, "usage": usage}
    return {
        "facts": facts,
        "answer_text": reply.output.answer_text,
        "used_template": False,
        "usage": usage,
    }
