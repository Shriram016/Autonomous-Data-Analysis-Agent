from datetime import date

from adaa.agent.context import load_context
from adaa.llm.adapters.fake import FakeAdapter
from tests.unit.fakes import fake_ask


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
    assert versions.agent_prompt.startswith("0.1.0 (")
    assert versions.answer_prompt.startswith("0.1.0 (")
