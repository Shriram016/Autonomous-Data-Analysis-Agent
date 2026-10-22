from datetime import date, datetime

from adaa.agent.context import load_context
from adaa.llm.adapters.fake import FakeAdapter
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult


def fake_ask(form: StructuredRequest) -> QueryResult:
    """Answers the start-up queries: orders by month (data date) and one per dimension."""
    if form.dimensions == ["month"]:
        rows: list[tuple[object, ...]] = [(datetime(2018, 8, 1), 6300), (datetime(2018, 9, 1), 16)]
    elif form.dimensions == ["customer_state"]:
        rows = [("SP", 1), ("RJ", 1)]
    else:
        rows = [(f"{form.dimensions[0]}_value", 1)]
    return QueryResult(columns=[], rows=rows, explanation=[], row_count=len(rows), elapsed_ms=0)


def test_context_is_built_from_the_runner() -> None:
    fake = FakeAdapter([])
    context = load_context(ask=fake_ask, adapter=fake)
    assert context.data_date == date(2018, 8, 31)
    assert context.catalogue.values["customer_state"] == ["RJ", "SP"]
    assert context.adapter is fake and context.ask is fake_ask


def test_agent_prompt_is_filled_with_the_catalogue_and_the_data_date() -> None:
    text = load_context(ask=fake_ask).agent_prompt.text
    assert "Today is 2018-08-31." in text
    assert "- `customer_state`: RJ (Rio de Janeiro), SP (São Paulo)" in text
    assert "{{" not in text


def test_versions_name_what_produced_the_answer() -> None:
    context = load_context(ask=fake_ask)
    versions = context.versions
    assert versions.semantic_layer == f"{context.layer.version} ({context.layer.fingerprint[:12]})"
    assert versions.agent_prompt.startswith("0.1.0 (") and versions.answer_prompt.startswith(
        "0.1.0 ("
    )
