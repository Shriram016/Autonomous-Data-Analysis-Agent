"""The agent graph and its one entry point, ask(question) (§0 M1.3, ADR 0011).

    start → understand → query → answer → end
                │          │
                └─ error ──┴──→ end

A minimal LangGraph graph: three nodes, and a stop edge after each node that can fail.
The answer node never fails (the template answer is its fallback). No checkpointer yet:
the state lives in memory for one question (checkpoints in Postgres come later).
"""

from collections.abc import Callable
from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from adaa.agent import nodes
from adaa.agent.context import AgentContext, get_context
from adaa.agent.facts import build_facts
from adaa.agent.notes import data_note
from adaa.agent.state import AgentState, FinishedAnswer, Table


def next_or_stop(next_node: str) -> Callable[[AgentState], str]:
    """The stop edge: go on to `next_node`, or end when the node set an error."""

    def route(state: AgentState) -> str:
        return END if state.error else next_node

    return route


def build_graph(context: AgentContext) -> CompiledStateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("understand", partial(nodes.understand, context=context))
    graph.add_node("query", partial(nodes.query, context=context))
    graph.add_node("answer", partial(nodes.answer, context=context))

    graph.add_edge(START, "understand")
    graph.add_conditional_edges("understand", next_or_stop("query"), ["query", END])
    graph.add_conditional_edges("query", next_or_stop("answer"), ["answer", END])
    graph.add_edge("answer", END)
    return graph.compile()


def finish(state: AgentState, context: AgentContext) -> FinishedAnswer:
    """The final state as the caller sees it."""
    common = {"question": state.question, "versions": context.versions, "usage": state.usage}
    if state.error:
        return FinishedAnswer(
            status="failed", text=state.error.message, error_kind=state.error.kind, **common
        )
    assert state.form and state.result and state.facts and state.answer_text is not None
    full = build_facts(state.result, state.form, context.layer, max_rows=state.result.row_count)
    return FinishedAnswer(
        status="answered",
        text=state.answer_text,
        table=Table(headers=full.headers, rows=full.rows),
        how=[*state.result.explanation, *state.value_notes, data_note(context.data_date)],
        used_template=state.used_template,
        **common,
    )


def ask(question: str, context: AgentContext | None = None) -> FinishedAnswer:
    """One English question in, one finished answer out."""
    context = context or get_context()
    final = build_graph(context).invoke(AgentState(question=question))
    return finish(AgentState.model_validate(final), context)
