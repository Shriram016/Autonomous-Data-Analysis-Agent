"""Shared fakes for the agent tests: a fake runner and a context built on it (no database)."""

from datetime import datetime

from adaa.agent.context import AgentContext, load_context
from adaa.llm.adapters.fake import FakeAdapter
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult


def query_result(*rows: tuple[object, ...]) -> QueryResult:
    return QueryResult(
        columns=[], rows=list(rows), explanation=[], row_count=len(rows), elapsed_ms=0
    )


def fake_ask(form: StructuredRequest) -> QueryResult:
    """Answers the start-up queries: orders by month (data date) and one per dimension."""
    if form.dimensions == ["month"]:
        return query_result((datetime(2018, 8, 1), 6300), (datetime(2018, 9, 1), 16))
    if form.dimensions == ["customer_state"]:
        return query_result(("SP", 1), ("RJ", 1))
    if form.dimensions == ["product_category"]:
        return query_result(("toys", 1), ("telephony", 1))
    return query_result((f"{form.dimensions[0]}_value", 1))


def fake_context(*replies: str | Exception) -> tuple[AgentContext, FakeAdapter]:
    """A context whose LLM gives these scripted replies, in order."""
    adapter = FakeAdapter(list(replies))
    return load_context(ask=fake_ask, adapter=adapter), adapter
