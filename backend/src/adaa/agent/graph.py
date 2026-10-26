"""The agent graph and its one entry point, ask(question) (§0 M1.3, ADR 0011).

    start → understand → query → answer → end
                │          │
                └─ error ──┴──→ end

A minimal LangGraph graph: three nodes, and a stop edge after each node that can fail.
The answer node never fails (the template answer is its fallback). No checkpointer yet:
the state lives in memory for one question (checkpoints in Postgres come later).
"""

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from adaa.agent import nodes
from adaa.agent.context import AgentContext, get_context
from adaa.agent.facts import build_chart, build_facts
from adaa.agent.notes import data_note, partial_period_note
from adaa.agent.state import AgentState, FinishedAnswer, Table


def next_or_stop(next_node: str) -> Callable[[AgentState], str]:
    """The stop edge: go on to `next_node`, or end when the node set an error."""

    def route(state: AgentState) -> str:
        return END if state.error else next_node

    return route


StepHook = Callable[[str], None]  # called with a node's name just before the node runs
Node = Callable[[AgentState, AgentContext], dict[str, Any]]


def with_hook(name: str, node: Node, context: AgentContext, on_step: StepHook | None) -> Any:
    """The node, bound to the context, announcing itself first (for progress events)."""

    def run(state: AgentState) -> dict[str, Any]:
        if on_step:
            on_step(name)
        return node(state, context)

    return run


def build_graph(context: AgentContext, on_step: StepHook | None = None) -> CompiledStateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("understand", with_hook("understand", nodes.understand, context, on_step))
    graph.add_node("query", with_hook("query", nodes.query, context, on_step))
    graph.add_node("answer", with_hook("answer", nodes.answer, context, on_step))

    graph.add_edge(START, "understand")
    graph.add_conditional_edges("understand", next_or_stop("query"), ["query", END])
    graph.add_conditional_edges("query", next_or_stop("answer"), ["answer", END])
    graph.add_edge("answer", END)
    return graph.compile()


def finish(state: AgentState, context: AgentContext) -> FinishedAnswer:
    """The final state as the caller sees it."""
    common = {
        "question": state.question,
        "versions": context.versions,
        "usage": state.usage,
        "form": state.form,  # also kept when a later step stopped: that is when it helps most
    }
    if state.error:
        return FinishedAnswer(
            status="failed", text=state.error.message, error_kind=state.error.kind, **common
        )
    assert state.form and state.result and state.facts and state.answer_text is not None
    full = build_facts(state.result, state.form, context.layer, max_rows=state.result.row_count)
    note = partial_period_note(state.form, context.data_date)  # made by code, after the guardrail
    return FinishedAnswer(
        status="answered",
        text=f"{state.answer_text} {note}" if note else state.answer_text,
        table=Table(headers=full.headers, rows=full.rows),
        chart=build_chart(state.result, state.form, context.layer),
        how=[*state.result.explanation, *state.value_notes, data_note(context.data_date)],
        used_template=state.used_template,
        **common,
    )


def ask(
    question: str, context: AgentContext | None = None, on_step: StepHook | None = None
) -> FinishedAnswer:
    """One English question in, one finished answer out.

    on_step: called with "understand", "query" or "answer" before that node runs; the worker
    uses it to publish progress events. The nodes themselves know nothing about it.
    """
    context = context or get_context()
    final = build_graph(context, on_step).invoke(AgentState(question=question))
    return finish(AgentState.model_validate(final), context)
