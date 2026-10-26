"""Shared fakes for the agent tests: a fake runner and a context built on it (no database)."""

from datetime import datetime

from adaa.agent.context import AgentContext, RouteFn, load_context
from adaa.agent.router import Route, RouteDecision
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


def fixed_route(route: Route = "numbers") -> RouteFn:
    """A router that always picks `route`, with no LLM call (the router has its own tests)."""
    return lambda question: RouteDecision(route=route, source="test")


def fake_context(
    *replies: str | Exception, route: RouteFn | None = None
) -> tuple[AgentContext, FakeAdapter]:
    """A context whose LLM gives these scripted replies, in order. The router picks
    `numbers` unless a test passes its own `route`."""
    adapter = FakeAdapter(list(replies))
    context = load_context(ask=fake_ask, adapter=adapter, route=route or fixed_route())
    return context, adapter
