"""The eval runner with the fake LLM and a fake runner: no database, no cost."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from adaa.evals.cases import EvalSet
from adaa.evals.run import RunReport, percentile, run_eval, save
from tests.unit.fakes import fake_context, query_result

CASES = EvalSet.model_validate(
    {
        "version": 1,
        "cases": [
            {
                "question": "What was the total revenue?",
                "id": "total_revenue",
                "kind": "simple",
                "expected_form": {"metric": "revenue"},
                "expected_sql": "SELECT 1",
            },
            {
                "question": "Revenue in Paris",
                "id": "revenue_in_paris",
                "kind": "must_stop",
                "expected_error": "value_not_found",
            },
        ],
    }
)
EXPECTED: dict[str, dict[str, Any]] = {
    "total_revenue": {"headers": ["Revenue"], "rows": [["R$ 100.00"]]},
    "revenue_in_paris": {"error": "value_not_found"},
}


def report() -> RunReport:
    replies = [
        json.dumps({"metric": "revenue"}),  # case 1: the plan
        json.dumps({"answer_text": "Revenue was R$ 100.00."}),  # case 1: the sentence
        json.dumps(  # case 2: a plan with Paris, stopped by the value check
            {
                "metric": "revenue",
                "filters": [{"dimension": "customer_state", "op": "=", "values": ["Paris"]}],
            }
        ),
    ]
    context, _ = fake_context(*replies)
    context = replace(context, ask=lambda form: query_result((Decimal(100),)))
    return run_eval(context, CASES, EXPECTED)


def test_both_cases_pass_and_are_counted() -> None:
    r = report()
    assert (r.passed, r.total) == (2, 2)
    assert r.by_kind == {"simple": "1/1", "must_stop": "1/1"}
    assert [x.reason for x in r.results] == ["result matches", "stopped with value_not_found"]
    assert r.template_answers == 0


def test_cost_and_versions_are_recorded() -> None:
    r = report()
    assert r.cost_usd == round(sum(x.cost_usd for x in r.results), 6) and r.cost_usd > 0
    assert r.models == {"agent": "claude-haiku-5-5", "answer": "claude-haiku-5-5"}
    assert r.versions.agent_prompt.startswith("0.1.0 (")


def test_a_run_is_saved_and_reads_back(tmp_path: Path) -> None:
    r = report()
    path = save(r, tmp_path)
    assert path.name.endswith(".json")
    assert RunReport.model_validate_json(path.read_text(encoding="utf-8")) == r


def test_percentile_is_nearest_rank() -> None:
    times = [float(i) for i in range(1, 21)]  # 1..20
    assert percentile(times, 0.50) == 10.0 and percentile(times, 0.95) == 19.0
