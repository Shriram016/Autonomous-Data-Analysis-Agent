"""Judge one eval case (§0 M1.7). Pure code: no LLM, no database.

The RESULT decides pass or fail: the agent's table must equal the stored right answer (from
the hand-written SQL), in any order unless the question asks for a sort. A must-stop case
passes only when the agent stopped with the expected error kind.

The FORM (the LLM's plan) is compared too, field by field, as hints that say where to look
("period: expected 2018-06-01 to 2018-08-31, got 2018-05-31 to 2018-08-31"). Hints never
change pass or fail: two different plans can give the same right answer.
"""

from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from adaa.agent.state import FinishedAnswer
from adaa.evals.cases import EvalCase
from adaa.semantic_layer.request import StructuredRequest


class Score(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    reason: str  # one plain line: why it passed or failed
    form_hints: list[str]  # where the plan differs from the expected plan (may be empty)


def form_hints(expected: StructuredRequest | None, got: StructuredRequest | None) -> list[str]:
    """Each field where the agent's plan differs from the expected plan."""
    if expected is None:
        return []
    if got is None:
        return ["no plan: the agent stopped before filling the form"]

    def filters(form: StructuredRequest) -> set[tuple[str, str, frozenset[str]]]:
        return {(f.dimension, f.op, frozenset(str(v) for v in f.values)) for f in form.filters}

    def period(form: StructuredRequest) -> str:
        return f"{form.period.start} to {form.period.end}" if form.period else "none (all data)"

    def sort(form: StructuredRequest) -> str:
        return f"{form.sort.by} {form.sort.direction}" if form.sort else "none"

    checks: list[tuple[str, Any, Any]] = [
        ("metric", expected.metric, got.metric),
        ("breakdown", sorted(expected.dimensions), sorted(got.dimensions)),
        ("filters", filters(expected), filters(got)),
        ("period", period(expected), period(got)),
        ("sort", sort(expected), sort(got)),
        ("limit", expected.limit, got.limit),
    ]
    return [f"{name}: expected {want}, got {have}" for name, want, have in checks if want != have]


def same_rows(expected: list[list[str]], got: list[list[str]], ordered: bool) -> bool:
    if ordered:
        return expected == got
    return Counter(map(tuple, expected)) == Counter(map(tuple, got))  # any order, same rows


def score_case(
    case: EvalCase,
    expected_answer: dict[str, Any],
    answer: FinishedAnswer,
    agent_form: StructuredRequest | None,
) -> Score:
    hints = form_hints(case.expected_form, agent_form)

    if case.expected_error:  # must stop
        if answer.status == "failed" and answer.error_kind == case.expected_error:
            return Score(passed=True, reason=f"stopped with {case.expected_error}", form_hints=[])
        got = answer.error_kind if answer.status == "failed" else "an answer"
        return Score(
            passed=False,
            reason=f"expected a stop ({case.expected_error}), got {got}",
            form_hints=[],
        )

    if answer.status == "failed":
        return Score(passed=False, reason=f"stopped with {answer.error_kind}", form_hints=hints)
    if answer.table is None:
        return Score(passed=False, reason="no table in the answer", form_hints=hints)

    assert case.expected_form is not None
    ordered = case.expected_form.sort is not None
    if same_rows(expected_answer["rows"], answer.table.rows, ordered):
        return Score(passed=True, reason="result matches", form_hints=hints)
    shown = len(answer.table.rows)
    wanted = len(expected_answer["rows"])
    detail = f"{shown} rows, expected {wanted}" if shown != wanted else "different values"
    return Score(passed=False, reason=f"result differs: {detail}", form_hints=hints)
