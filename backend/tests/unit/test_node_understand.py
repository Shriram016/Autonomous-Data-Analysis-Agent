import json
from typing import Any

from adaa.agent.nodes import NOT_UNDERSTOOD, understand
from adaa.agent.state import AgentState
from adaa.llm.types import LlmUnavailableError
from tests.unit.fakes import fake_context


def form_json(**fields: object) -> str:
    return json.dumps(fields)


def run(question: str, *replies: str | Exception) -> dict[str, Any]:
    context, _ = fake_context(*replies)
    return understand(AgentState(question=question), context)


def test_a_good_form() -> None:
    update = run("Total revenue", form_json(metric="revenue"))
    assert update["form"].metric == "revenue"
    assert update["value_notes"] == [] and "error" not in update
    assert update["usage"].cost_usd > 0


def test_the_model_sees_the_agent_prompt_and_the_question() -> None:
    context, adapter = fake_context(form_json(metric="revenue"))
    understand(AgentState(question="Total revenue"), context)
    system, user = adapter.calls[0].messages
    assert system.content == context.agent_prompt.text and user.content == "Total revenue"


def test_a_close_value_is_fixed_and_noted() -> None:
    reply = form_json(
        metric="revenue", filters=[{"dimension": "product_category", "op": "=", "values": ["toy"]}]
    )
    update = run("Revenue for toy", reply)
    assert update["form"].filters[0].values == ["toys"]
    assert update["value_notes"] == ["I read 'toy' as 'toys'."]


def test_an_unknown_value_stops_with_a_plain_message() -> None:
    reply = form_json(
        metric="revenue", filters=[{"dimension": "customer_state", "op": "=", "values": ["Paris"]}]
    )
    error = run("Revenue in Paris", reply)["error"]
    assert error.kind == "value_not_found"
    assert "No customer_state called 'Paris'" in error.message


def test_llm_outage() -> None:
    error = run("Total revenue", LlmUnavailableError("The AI service is busy (rate limit)."))[
        "error"
    ]
    assert error.kind == "llm_unavailable" and "busy" in error.message


def test_bad_form_after_the_retry() -> None:
    error = run("Total revenue", "not json", "still not json")["error"]
    assert error.kind == "llm_output" and error.message == NOT_UNDERSTOOD
