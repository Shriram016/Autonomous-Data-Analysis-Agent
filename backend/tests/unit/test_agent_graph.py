"""The whole graph end to end, with the fake LLM and a fake runner: no database, no cost."""

import json
from dataclasses import replace
from decimal import Decimal

from adaa.agent.context import AgentContext
from adaa.agent.graph import ask
from adaa.llm.types import LlmUnavailableError
from adaa.semantic_layer.compiler import CompileError
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult
from tests.unit.fakes import fake_context, query_result

REVENUE_BY_STATE = json.dumps(
    {
        "metric": "revenue",
        "dimensions": ["customer_state"],
        "period": {"start": "2017-01-01", "end": "2017-12-31"},
    }
)
ROWS = QueryResult(
    columns=["customer_state", "revenue"],
    rows=[("SP", Decimal("2136258.96")), ("RJ", Decimal("876499.71"))],
    explanation=["Revenue = item price, excluding freight.", "Period: 2017-01-01 to 2017-12-31."],
    row_count=2,
    elapsed_ms=10,
)


def with_rows(context: AgentContext, rows: QueryResult = ROWS) -> AgentContext:
    return replace(context, ask=lambda form: rows)


def sentence(text: str) -> str:
    return json.dumps({"answer_text": text})


def test_a_good_answer() -> None:
    context, adapter = fake_context(REVENUE_BY_STATE, sentence("SP led 2017 with R$ 2,136,258.96."))
    result = ask("Revenue by state in 2017", with_rows(context))
    assert result.status == "answered" and result.used_template is False
    assert result.text == "SP led 2017 with R$ 2,136,258.96."
    assert result.table is not None
    assert result.table.rows == [
        ["SP (São Paulo)", "R$ 2,136,258.96"],
        ["RJ (Rio de Janeiro)", "R$ 876,499.71"],
    ]
    assert result.how[0] == "Revenue = item price, excluding freight."
    assert result.how[-1] == "Data as of 2018-08-31."
    assert result.versions == context.versions
    assert len(adapter.calls) == 2  # one agent call, one answer call
    assert result.usage.input_tokens == 2_000  # both calls added up (1,000 each, fake)


def test_a_guardrail_failure_gives_the_template() -> None:
    context, _ = fake_context(REVENUE_BY_STATE, sentence("SP made 71% of it."))
    result = ask("Revenue by state in 2017", with_rows(context))
    assert result.status == "answered" and result.used_template is True
    assert result.text.startswith("Revenue by customer state (2 rows):")


def test_an_unknown_value_stops_after_understand() -> None:
    paris = json.dumps(
        {
            "metric": "revenue",
            "filters": [{"dimension": "customer_state", "op": "=", "values": ["Paris"]}],
        }
    )
    context, adapter = fake_context(paris)

    def must_not_run(form: StructuredRequest) -> QueryResult:
        raise AssertionError("the query must not run")

    result = ask("Revenue in Paris", replace(context, ask=must_not_run))
    assert result.status == "failed" and result.error_kind == "value_not_found"
    assert "No customer_state called 'Paris'" in result.text
    assert result.table is None and len(adapter.calls) == 1  # no answer call either


def test_a_compiler_refusal_stops_after_query() -> None:
    form = json.dumps({"metric": "revenue", "dimensions": ["payment_type"]})
    context, adapter = fake_context(form)

    def refuse(form: StructuredRequest) -> QueryResult:
        raise CompileError("Revenue can't be split by payment type.")

    result = ask("Revenue by payment type", replace(context, ask=refuse))
    assert (
        result.error_kind == "compile_refused"
        and result.text == "Revenue can't be split by payment type."
    )
    assert len(adapter.calls) == 1


def test_an_llm_outage_fails_with_a_plain_message() -> None:
    context, _ = fake_context(LlmUnavailableError("The AI service is busy (rate limit)."))
    result = ask("Total revenue", with_rows(context, query_result((Decimal(1),))))
    assert result.status == "failed" and result.error_kind == "llm_unavailable"
    assert result.text == "The AI service is busy (rate limit)."


def test_value_notes_reach_the_how_lines() -> None:
    toy = json.dumps(
        {
            "metric": "revenue",
            "filters": [{"dimension": "product_category", "op": "=", "values": ["toy"]}],
        }
    )
    context, _ = fake_context(toy, sentence("Toys made R$ 100.00."))
    result = ask("Revenue for toy", with_rows(context, query_result((Decimal(100),))))
    assert "I read 'toy' as 'toys'." in result.how


def test_the_progress_hook_announces_each_node_in_order() -> None:
    context, _ = fake_context(REVENUE_BY_STATE, sentence("SP led."))
    seen: list[str] = []
    ask("Revenue by state in 2017", with_rows(context), on_step=seen.append)
    assert seen == ["understand", "query", "answer"]


def test_the_progress_hook_stops_with_the_graph() -> None:
    context, _ = fake_context(LlmUnavailableError("down"))
    seen: list[str] = []
    ask("Total revenue", with_rows(context), on_step=seen.append)
    assert seen == ["understand"]  # the error stopped the graph after the first node


# --- the plan in the finished answer (M1.7) ---


def test_an_answer_carries_the_plan() -> None:
    context, _ = fake_context(REVENUE_BY_STATE, sentence("SP led."))
    result = ask("Revenue by state in 2017", with_rows(context))
    assert result.form is not None and result.form.metric == "revenue"
    assert result.form.dimensions == ["customer_state"]


def test_a_compiler_refusal_still_carries_the_plan() -> None:
    context, _ = fake_context(json.dumps({"metric": "revenue", "dimensions": ["payment_type"]}))

    def refuse(form: StructuredRequest) -> QueryResult:
        raise CompileError("Revenue can't be split by payment type.")

    result = ask("Revenue by payment type", replace(context, ask=refuse))
    assert result.status == "failed" and result.form is not None
    assert result.form.dimensions == ["payment_type"]  # the hint shows what the LLM planned


def test_a_value_check_stop_carries_no_plan() -> None:
    paris = json.dumps(
        {
            "metric": "revenue",
            "filters": [{"dimension": "customer_state", "op": "=", "values": ["Paris"]}],
        }
    )
    context, _ = fake_context(paris)
    result = ask("Revenue in Paris", with_rows(context))
    assert result.error_kind == "value_not_found" and result.form is None  # no checked plan
