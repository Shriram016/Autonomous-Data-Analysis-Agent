"""The three nodes of the agent graph: understand → query → answer (§0 M1.3, step 6).

Each node takes the state and the context and returns ONLY the fields it fills; the graph
merges them into the state. A node that fails returns an `error` (a kind + a plain message)
and the graph stops. The nodes add no new checks: they run the existing ones in order.
"""

from typing import Any

from adaa.agent.context import AgentContext
from adaa.agent.state import AgentError, AgentState
from adaa.agent.values import ValueNotFoundError, check_filters
from adaa.llm.adapters.base import Message
from adaa.llm.complete import complete
from adaa.llm.types import LlmOutputError, LlmUnavailableError
from adaa.semantic_layer.request import StructuredRequest

NOT_UNDERSTOOD = "I could not turn the question into a request. Please rephrase it."


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
