from decimal import Decimal

import pytest
from pydantic import ValidationError

from adaa.agent.state import AgentError, AgentState, FinishedAnswer, Table, Versions
from adaa.llm.types import Usage
from adaa.semantic_layer.runner import QueryResult

VERSIONS = Versions(
    semantic_layer="0.3.3 (73fe01005fa8)",
    agent_prompt="0.1.0 (a1b2c3d4e5f6)",
    answer_prompt="0.1.0 (f6e5d4c3b2a1)",
)
USAGE = Usage(input_tokens=3_100, output_tokens=120, thinking_tokens=0, cost_usd=0.00037)


def test_an_answered_question() -> None:
    answer = FinishedAnswer(
        question="Revenue by state in 2017",
        status="answered",
        text="SP led 2017 with R$ 2,136,258.96.",
        table=Table(
            headers=["Customer state", "Revenue"], rows=[["SP (São Paulo)", "R$ 2,136,258.96"]]
        ),
        how=["Revenue = item price, excluding freight.", "Data as of 2018-08-31."],
        versions=VERSIONS,
        usage=USAGE,
    )
    assert answer.error_kind is None and answer.used_template is False


def test_a_failed_question() -> None:
    answer = FinishedAnswer(
        question="Revenue in Paris",
        status="failed",
        text="No customer_state called 'Paris' in the data.",
        error_kind="value_not_found",
        versions=VERSIONS,
        usage=USAGE,
    )
    assert answer.table is None and answer.how == []


def test_answer_turns_into_json_and_back_with_no_loss() -> None:
    answer = FinishedAnswer(
        question="Total revenue",
        status="answered",
        text="Revenue: R$ 13,221,498.11.",
        table=Table(headers=["Revenue"], rows=[["R$ 13,221,498.11"]]),
        how=["Data as of 2018-08-31."],
        used_template=True,
        versions=VERSIONS,
        usage=USAGE,
    )
    assert FinishedAnswer.model_validate_json(answer.model_dump_json()) == answer


def test_state_starts_with_only_the_question() -> None:
    state = AgentState(question="Total revenue")
    assert state.form is None and state.value_notes == [] and state.error is None
    assert state.usage.cost_usd == 0 and state.state_version == 2 and state.route is None


def test_state_is_checked_at_run_time() -> None:
    with pytest.raises(ValidationError):
        AgentState.model_validate({"question": "Total revenue", "used_template": "maybe"})
    with pytest.raises(ValidationError):  # a typo in a field name is caught too
        AgentState.model_validate({"question": "Total revenue", "eror": "x"})


def test_state_with_a_result_survives_a_save_and_load() -> None:
    """What a checkpoint will do: save the state, load it back, get the same values."""
    state = AgentState(
        question="Revenue by state",
        result=QueryResult(
            columns=["customer_state", "revenue"],
            rows=[("SP", Decimal("2136258.96"))],
            explanation=["Revenue = item price, excluding freight."],
            row_count=1,
            elapsed_ms=12,
        ),
        error=AgentError(kind="query_timeout", message="The query took too long."),
    )
    loaded = AgentState.model_validate(state.model_dump())
    assert loaded == state
