import json
from decimal import Decimal
from typing import Any

import pytest

from adaa.agent.nodes import answer
from adaa.agent.state import AgentState
from adaa.llm.types import LlmUnavailableError
from adaa.semantic_layer.request import StructuredRequest
from tests.unit.fakes import fake_context, query_result

FORM = StructuredRequest.model_validate(
    {
        "metric": "revenue",
        "dimensions": ["customer_state"],
        "period": {"start": "2017-01-01", "end": "2017-12-31"},
    }
)
ROWS = query_result(("SP", Decimal("2136258.96")), ("RJ", Decimal("876499.71")))
STATE = AgentState(question="Revenue by state in 2017", form=FORM, result=ROWS)


def reply(text: str) -> str:
    return json.dumps({"answer_text": text})


def run(*replies: str | Exception) -> tuple[dict[str, Any], Any]:
    context, adapter = fake_context(*replies)
    return answer(STATE, context), adapter


def test_a_good_sentence_is_used() -> None:
    text = "In 2017, SP led with R$ 2,136,258.96, ahead of RJ with R$ 876,499.71."
    update, _ = run(reply(text))
    assert update["answer_text"] == text and update["used_template"] is False
    assert update["facts"].total == "R$ 3,012,758.67"
    assert update["usage"].cost_usd > 0


def test_the_model_sees_the_question_and_the_formatted_result() -> None:
    _, adapter = run(reply("SP led."))
    system, user = adapter.calls[0].messages
    assert "Never calculate" in system.content
    assert user.content.startswith("Question: Revenue by state in 2017\n\nResult (2 rows):")
    assert "SP (São Paulo) | R$ 2,136,258.96" in user.content


def test_a_number_not_in_the_data_gives_the_template(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING", logger="adaa.agent")
    update, _ = run(reply("SP made 71% of the revenue."))  # a calculated share
    assert update["used_template"] is True
    assert update["answer_text"].startswith("Revenue by customer state (2 rows): SP (São Paulo)")
    assert "answer_guardrail_failed bad_numbers=1" in caplog.text
    assert "71%" not in caplog.text  # the log holds counts, never the text
    assert update["usage"].cost_usd > 0  # the paid call is still counted


@pytest.mark.parametrize(
    ("bad_reply", "reason"),
    [
        ("not json", "LlmOutputError"),
        (LlmUnavailableError("The AI service is down."), "LlmUnavailableError"),
    ],
)
def test_an_llm_failure_gives_the_template(
    caplog: pytest.LogCaptureFixture, bad_reply: str | Exception, reason: str
) -> None:
    caplog.set_level("WARNING", logger="adaa.agent")
    update, adapter = run(bad_reply)
    assert update["used_template"] is True and "error" not in update  # never stops the graph
    assert len(adapter.calls) == 1  # max_attempts 1: no second paid call
    assert f"answer_llm_failed reason={reason}" in caplog.text


def test_years_from_the_question_are_allowed() -> None:
    update, _ = run(reply("In 2017, SP led with R$ 2,136,258.96."))
    assert update["used_template"] is False


def test_only_the_top_rows_go_to_the_llm() -> None:
    many = query_result(*[(f"S{i}", Decimal(100 - i)) for i in range(27)])
    context, adapter = fake_context(reply("S0 led."))
    answer(STATE.model_copy(update={"result": many}), context)
    assert "Result (top 20 of 27 rows):" in adapter.calls[0].messages[1].content
