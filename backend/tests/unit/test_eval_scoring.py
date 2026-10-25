from typing import Any

from adaa.agent.state import NO_USAGE, FinishedAnswer, Table, Versions
from adaa.evals.cases import EvalCase
from adaa.evals.scoring import form_hints, score_case
from adaa.semantic_layer.request import StructuredRequest

VERSIONS = Versions(semantic_layer="x", agent_prompt="y", answer_prompt="z")


def case(**fields: Any) -> EvalCase:
    base = {"id": "c", "kind": "breakdown", "question": "q"}
    if "expected_error" not in fields:
        base["expected_sql"] = "SELECT 1"
    return EvalCase.model_validate(base | fields)


def form(**fields: Any) -> StructuredRequest:
    return StructuredRequest.model_validate(fields)


def answered(*rows: list[str]) -> FinishedAnswer:
    return FinishedAnswer(
        question="q",
        status="answered",
        text="t",
        table=Table(headers=["h"], rows=list(rows)),
        versions=VERSIONS,
        usage=NO_USAGE,
    )


def stopped(kind: Any) -> FinishedAnswer:
    return FinishedAnswer(
        question="q", status="failed", text="t", error_kind=kind, versions=VERSIONS, usage=NO_USAGE
    )


BY_STATE = case(expected_form={"metric": "revenue", "dimensions": ["customer_state"]})
EXPECTED = {"rows": [["SP", "R$ 5.00"], ["RJ", "R$ 3.00"]]}


def test_a_right_answer_passes() -> None:
    score = score_case(BY_STATE, EXPECTED, answered(["SP", "R$ 5.00"], ["RJ", "R$ 3.00"]), None)
    assert score.passed and score.reason == "result matches"


def test_rows_in_another_order_pass_when_no_sort_was_asked() -> None:
    got = answered(["RJ", "R$ 3.00"], ["SP", "R$ 5.00"])
    assert score_case(BY_STATE, EXPECTED, got, None).passed


def test_a_wrong_number_fails() -> None:
    score = score_case(BY_STATE, EXPECTED, answered(["SP", "R$ 5.00"], ["RJ", "R$ 9.99"]), None)
    assert not score.passed and score.reason == "result differs: different values"


def test_a_missing_row_fails_with_the_counts() -> None:
    score = score_case(BY_STATE, EXPECTED, answered(["SP", "R$ 5.00"]), None)
    assert not score.passed and score.reason == "result differs: 1 rows, expected 2"


def test_order_matters_when_the_question_asks_for_a_sort() -> None:
    top = case(
        kind="top",
        expected_form={
            "metric": "revenue",
            "dimensions": ["product_category"],
            "sort": {"by": "revenue"},
            "limit": 2,
        },
    )
    expected = {"rows": [["a", "2"], ["b", "1"]]}
    assert score_case(top, expected, answered(["a", "2"], ["b", "1"]), None).passed
    assert not score_case(top, expected, answered(["b", "1"], ["a", "2"]), None).passed


def test_a_stop_where_an_answer_was_expected_fails() -> None:
    score = score_case(BY_STATE, EXPECTED, stopped("compile_refused"), None)
    assert not score.passed and score.reason == "stopped with compile_refused"


def test_a_must_stop_case() -> None:
    paris = case(kind="must_stop", expected_error="value_not_found")
    assert score_case(paris, {"error": "value_not_found"}, stopped("value_not_found"), None).passed
    wrong_kind = score_case(paris, {}, stopped("llm_output"), None)
    assert (
        not wrong_kind.passed
        and wrong_kind.reason == "expected a stop (value_not_found), got llm_output"
    )
    answered_anyway = score_case(paris, {}, answered(["x"]), None)
    assert not answered_anyway.passed and "got an answer" in answered_anyway.reason


def test_hints_name_each_field_that_differs() -> None:
    expected = form(metric="orders", period={"start": "2018-06-01", "end": "2018-08-31"})
    got = form(metric="revenue", period={"start": "2018-05-31", "end": "2018-08-31"})
    assert form_hints(expected, got) == [
        "metric: expected orders, got revenue",
        "period: expected 2018-06-01 to 2018-08-31, got 2018-05-31 to 2018-08-31",
    ]


def test_hints_never_change_the_score() -> None:
    sorted_anyway = form(metric="revenue", dimensions=["customer_state"], sort={"by": "revenue"})
    score = score_case(
        BY_STATE, EXPECTED, answered(["SP", "R$ 5.00"], ["RJ", "R$ 3.00"]), sorted_anyway
    )
    assert score.passed and score.form_hints == ["sort: expected none, got revenue desc"]


def test_same_filters_in_another_order_give_no_hint() -> None:
    a = form(
        metric="revenue",
        filters=[{"dimension": "customer_state", "op": "in", "values": ["SP", "RJ"]}],
    )
    b = form(
        metric="revenue",
        filters=[{"dimension": "customer_state", "op": "in", "values": ["RJ", "SP"]}],
    )
    assert form_hints(a, b) == []
