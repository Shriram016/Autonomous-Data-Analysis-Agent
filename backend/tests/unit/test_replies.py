"""The quick-route replies with the fake LLM: no database, no key, no cost."""

import json
import logging
from datetime import date

import pytest

from adaa.agent.replies import (
    CLARIFY_FALLBACK,
    EXAMPLES,
    OFF_TOPIC_TEXT,
    REFUSE_FALLBACK,
    DataFacts,
    QuickReply,
    QuickRoute,
    build_reply_prompts,
    make_reply,
)
from adaa.llm.adapters.fake import FakeAdapter
from adaa.llm.types import LlmUnavailableError
from adaa.semantic_layer.definitions import load

LAYER = load()
FACTS = DataFacts(
    first_month=date(2016, 9, 1), last_month=date(2018, 10, 1), data_date=date(2018, 8, 31)
)
PROMPTS = build_reply_prompts(LAYER, FACTS)


def first_three(items: list[str], n: int) -> list[str]:
    return items[:n]  # a fixed "random" pick


def reply(
    route: QuickRoute, *llm: str | Exception, question: str = "q"
) -> tuple[QuickReply, FakeAdapter]:
    adapter = FakeAdapter(list(llm))
    return make_reply(route, question, PROMPTS, LAYER, FACTS, adapter, first_three), adapter


def test_clarify_gives_the_message_and_the_options_as_buttons() -> None:
    form = {"message": "Best by what? Pick one:", "options": ["Top 5 by revenue", "Top 5 by items"]}
    result, adapter = reply("clarify", json.dumps(form), question="Best products?")
    assert result.text == "Best by what? Pick one:"
    assert result.suggestions == ["Top 5 by revenue", "Top 5 by items"]
    assert result.usage.input_tokens == 1_000 and not result.used_fallback
    sent = adapter.calls[0]
    assert sent.job.job == "reply" and "Dimensions allowed" in sent.messages[0].content


def test_clarify_needs_two_or_three_options() -> None:
    one_option = {"message": "Best by what?", "options": ["Top 5 by revenue"]}
    result, _ = reply("clarify", json.dumps(one_option))
    assert result.text == CLARIFY_FALLBACK and result.used_fallback  # no retry (max_attempts 1)


def test_refuse_names_the_missing_data_and_one_suggestion() -> None:
    form = {"missing_data": "The data has no costs.", "suggestion": "Revenue in 2017?"}
    result, _ = reply("refuse", json.dumps(form))
    assert result.text == "The data has no costs." and result.suggestions == ["Revenue in 2017?"]


@pytest.mark.parametrize(
    ("form", "starts"),
    [
        ({"topic": "data_overview"}, "I answer questions about the store's orders from 2016-09"),
        ({"topic": "date_range"}, "The data has orders from 2016-09 to 2018-10."),
        ({"topic": "definition", "metric": "revenue"}, "Revenue: Product sales"),
        ({"topic": "definition", "metric": "profit"}, "I have no metric called profit."),
    ],
)
def test_metadata_facts_come_from_code(form: dict[str, str], starts: str) -> None:
    result, _ = reply("metadata", json.dumps(form))
    assert result.text.startswith(starts) and result.suggestions == []


def test_a_definition_states_the_status_rule() -> None:
    revenue, _ = reply("metadata", json.dumps({"topic": "definition", "metric": "revenue"}))
    assert revenue.text.endswith("Delivered orders only, unless you ask for an order status.")
    rate = json.dumps({"topic": "definition", "metric": "cancellation_rate"})
    assert reply("metadata", rate)[0].text.endswith("Orders in every status.")


def test_off_topic_needs_no_llm() -> None:
    result, adapter = reply("off_topic")
    assert result.text == OFF_TOPIC_TEXT and result.suggestions == EXAMPLES[:3]
    assert adapter.calls == []


def test_off_topic_examples_are_random_three_of_six() -> None:
    result = make_reply("off_topic", "q", PROMPTS, LAYER, FACTS)
    assert len(result.suggestions) == 3 and set(result.suggestions) <= set(EXAMPLES)
    assert len(EXAMPLES) == 6


@pytest.mark.parametrize(
    ("route", "text", "buttons"),
    [("clarify", CLARIFY_FALLBACK, 0), ("refuse", REFUSE_FALLBACK, 3), ("metadata", None, 0)],
)
def test_an_llm_failure_gives_a_code_made_reply(
    route: QuickRoute, text: str | None, buttons: int, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="adaa.agent")
    result, _ = reply(route, LlmUnavailableError("down"))
    assert result.used_fallback and len(result.suggestions) == buttons
    assert result.text == (text or result.text) and result.text.startswith(text or "I answer")
    assert f"reply_failed route={route} reason=LlmUnavailableError" in caplog.text
    assert f"quick_reply route={route} used_fallback=True" in caplog.text


def test_prompts_are_filled_from_the_semantic_layer() -> None:
    for prompt in (PROMPTS.clarify, PROMPTS.refuse, PROMPTS.metadata):
        assert prompt.version == "0.1.0" and "{{" not in prompt.text
    assert "repeat_customer_rate" in PROMPTS.metadata.text
    assert "orders from 2016-09 to 2018-08-31" in PROMPTS.clarify.text
