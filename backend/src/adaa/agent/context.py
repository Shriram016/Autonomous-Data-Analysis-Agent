"""What every question needs, loaded once per worker process (§0 M1.3, step 6c).

The semantic layer, the value catalogue, the data date and the two filled prompts are the
same for every question, and the catalogue and the data date need database queries. So
they are loaded once and kept: get_context() returns the same copy for the whole process.
Each worker process has its own copy (processes don't share memory); it is small.

The nodes never call the database or an LLM provider directly. They go through `ask` and
`adapter` here, so a test builds a context with a fake runner and the fake LLM — no
database, no key, no cost.

Known limit: after a data reload (the daily load, M3) the catalogue and the data date are
old until the worker restarts. Later: the load publishes a new data version in Redis and
each worker reloads its copy.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from functools import cache

from adaa.agent.notes import find_data_date
from adaa.agent.prompts import Prompt, load_prompt, semantic_values
from adaa.agent.router import RouteDecision, RouterTexts, build_router_texts, route_question
from adaa.agent.state import Versions
from adaa.agent.values import ValueCatalogue, build_catalogue
from adaa.llm.adapters.base import Adapter
from adaa.semantic_layer.definitions import SemanticLayer, load
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult, answer_request

Ask = Callable[[StructuredRequest], QueryResult]  # runs one form and returns its rows
RouteFn = Callable[[str], RouteDecision]  # picks one question's route


@dataclass(frozen=True)
class AgentContext:
    layer: SemanticLayer
    catalogue: ValueCatalogue
    data_date: date
    agent_prompt: Prompt  # filled: metrics, dimensions, values, data date
    answer_prompt: Prompt
    router_texts: RouterTexts  # the router's prompt (Haiku) and instructions (Jev)
    ask: Ask  # real: the M1.1 runner as adaa_query; tests: a fake
    route: RouteFn  # real: route_question (Jev, then Haiku); tests: a fixed route
    adapter: Adapter | None = None  # None: the adapter config/llm.yaml names; tests: fake

    @property
    def versions(self) -> Versions:
        def short(version: str, fingerprint: str) -> str:
            return f"{version} ({fingerprint[:12]})"

        return Versions(
            semantic_layer=short(self.layer.version, self.layer.fingerprint),
            agent_prompt=short(self.agent_prompt.version, self.agent_prompt.fingerprint),
            answer_prompt=short(self.answer_prompt.version, self.answer_prompt.fingerprint),
            router_prompt=short(
                self.router_texts.prompt.version, self.router_texts.prompt.fingerprint
            ),
        )


def load_context(
    ask: Ask | None = None, adapter: Adapter | None = None, route: RouteFn | None = None
) -> AgentContext:
    layer = load()
    run = ask or (lambda form: answer_request(form, layer))
    catalogue = build_catalogue(layer, run)
    data_date = find_data_date(layer, run)
    texts = build_router_texts(layer, data_date)
    return AgentContext(
        layer=layer,
        catalogue=catalogue,
        data_date=data_date,
        agent_prompt=load_prompt("agent", semantic_values(layer, catalogue, data_date)),
        answer_prompt=load_prompt("answer", {}),
        router_texts=texts,
        ask=run,
        route=route or (lambda question: route_question(question, texts, adapter=adapter)),
        adapter=adapter,
    )


@cache
def get_context() -> AgentContext:
    """The real context, loaded on first use and then kept for the whole process."""
    return load_context()
