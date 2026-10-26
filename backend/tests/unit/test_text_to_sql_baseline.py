"""The text-to-SQL baseline (experiment, M2 step 3a) with the fake LLM: no database, no cost."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from adaa.agent.prompts import Prompt
from adaa.evals.cases import load_cases
from adaa.llm.adapters.fake import FakeAdapter
from adaa.llm.types import LlmUnavailableError
from adaa.semantic_layer.definitions import load
from experiments.text_to_sql import baseline
from experiments.text_to_sql.baseline import (
    SqlForm,
    Variant,
    ask_baseline,
    build_prompt,
    is_select,
    tables_text,
)
from experiments.text_to_sql.run import BaselineRun, run_baseline, save, to_json

COLUMNS = [
    ("orders", "order_id", "text", True),
    ("orders", "order_status", "text", False),
    ("order_items", "order_id", "text", True),
    ("order_items", "price", "numeric", False),
]
TODAY = date(2018, 8, 31)


def test_tables_are_described_one_line_each() -> None:
    assert tables_text(COLUMNS) == (
        "- orders(order_id text KEY, order_status text)\n"
        "- order_items(order_id text KEY, price numeric)"
    )


def test_variant_b_adds_the_business_rules() -> None:
    a = build_prompt("A", COLUMNS, load(), TODAY)
    b = build_prompt("B", COLUMNS, load(), TODAY)
    assert "{{" not in a.text and "{{" not in b.text
    assert "Business rules" not in a.text and "Freight is not revenue" in b.text
    for prompt in (a, b):
        assert "Today is 2018-08-31." in prompt.text
        assert "order_items.order_id = orders.order_id" in prompt.text  # how tables connect


def test_the_form_holds_a_query_or_a_reason_never_both() -> None:
    assert SqlForm(sql="SELECT 1").sql == "SELECT 1"
    with pytest.raises(ValidationError, match="exactly one"):
        SqlForm(sql="SELECT 1", cannot_answer="no")
    with pytest.raises(ValidationError, match="exactly one"):
        SqlForm()


@pytest.mark.parametrize(
    ("sql", "ok"),
    [
        ("SELECT 1", True),
        ("  with x as (select 1) select * from x", True),
        ("DELETE FROM orders", False),
        ("", False),
    ],
)
def test_only_select_queries_run(sql: str, ok: bool) -> None:
    assert is_select(sql) is ok


def answer_with(reply: str | Exception, monkeypatch: pytest.MonkeyPatch) -> baseline.BaselineAnswer:
    ran: list[str] = []

    def fake_run(sql: str, conninfo: str) -> tuple[list[tuple[object, ...]], str | None]:
        ran.append(sql)
        return [(42,)], None

    monkeypatch.setattr(baseline, "run_sql", fake_run)
    prompt = build_prompt("A", COLUMNS, load(), TODAY)
    return ask_baseline("q", "A", prompt, "conninfo", adapter=FakeAdapter([reply]))


def test_a_query_runs_and_its_rows_come_back(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = answer_with(json.dumps({"sql": "SELECT count(*) FROM orders"}), monkeypatch)
    assert answer.rows == [(42,)] and answer.error is None
    assert answer.usage.input_tokens == 1_000  # the fake's fixed count


def test_cannot_answer_runs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = answer_with(json.dumps({"cannot_answer": "No cost data."}), monkeypatch)
    assert answer.cannot_answer == "No cost data." and answer.rows == [] and answer.error is None


def test_a_write_is_never_run(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = answer_with(json.dumps({"sql": "DROP TABLE orders"}), monkeypatch)
    assert answer.error == "not_a_select" and answer.rows == []


def test_an_llm_failure_is_recorded_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = answer_with(LlmUnavailableError("down"), monkeypatch)
    assert answer.error == "llm_failed" and answer.sql is None


# --- the run script (saves raw answers; scoring reads them later) ---


def test_database_values_are_saved_exactly() -> None:
    assert to_json(Decimal("13221498.11")) == "13221498.11"  # exact text, not a float
    assert to_json(date(2017, 3, 1)) == "2017-03-01"
    assert to_json(None) is None and to_json(42) == 42


def test_every_numbers_case_runs_once_per_variant(tmp_path: Path) -> None:
    asked: list[tuple[str, str]] = []

    def fake_ask(question: str, variant: Variant, prompt: Prompt) -> baseline.BaselineAnswer:
        asked.append((question, variant))
        return baseline.BaselineAnswer(
            question=question, variant=variant, sql="SELECT 1", rows=[(1,)]
        )

    prompts: dict[Variant, Prompt] = {
        "A": build_prompt("A", COLUMNS, load(), TODAY),
        "B": build_prompt("B", COLUMNS, load(), TODAY),
    }
    cases = load_cases()
    run = run_baseline(cases, prompts, fake_ask)
    numbers = [c for c in cases.cases if c.expected_route == "numbers"]
    assert len(run.results) == 2 * len(numbers) == len(asked)
    assert {r.variant for r in run.results} == {"A", "B"} and run.cases_version == cases.version
    path = save(run, tmp_path)
    assert BaselineRun.model_validate_json(path.read_text(encoding="utf-8")) == run
