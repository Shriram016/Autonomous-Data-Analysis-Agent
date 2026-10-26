"""Run each case's hand-written SQL once and store the right answers (§0 M1.7).

The answers come from SQL written straight from the tables, NOT from our compiler, so the
eval tests the compiler too. They are stored as the user sees them (the same formatting as
the answer table), in eval/questions/expected_results.json. That file is generated, never
edited by hand: after a case or a definition changes, run this again and review the git
diff, which shows exactly which numbers moved.

Runs as adaa_query (read-only, 5 s per query), like every other question.

Run from backend/:  uv run python -m adaa.evals.expected
"""

import json
from typing import Any

import psycopg

from adaa.agent.facts import build_headers, format_row
from adaa.agent.notes import find_data_date, find_data_span
from adaa.agent.replies import OFF_TOPIC_TEXT, DataFacts, metadata_text
from adaa.evals.cases import EvalCase, load_cases
from adaa.semantic_layer.definitions import SemanticLayer, load
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult, answer_request
from adaa.settings import REPO_ROOT, get_settings

RESULTS_FILE = REPO_ROOT / "eval" / "questions" / "expected_results.json"


def expected_answer(
    case: EvalCase, layer: SemanticLayer, conn: psycopg.Connection, facts: DataFacts
) -> dict[str, Any]:
    # Quick routes (M2 step 2d): the route, and the text where code writes it exactly.
    if case.expected_route == "metadata":
        assert case.expected_topic is not None
        return {"route": "metadata", "text": metadata_text(case.expected_topic, layer, facts)}
    if case.expected_route == "off_topic":
        return {"route": "off_topic", "text": OFF_TOPIC_TEXT}
    if case.expected_route != "numbers":  # clarify, refuse: the LLM writes the text
        return {"route": case.expected_route}
    if case.expected_error:
        return {"error": case.expected_error}
    assert case.expected_form and case.expected_sql
    form = case.expected_form
    rows = conn.execute(case.expected_sql).fetchall()
    return {  # the same formatting as the answer table; a comparison's SQL returns
        # (breakdowns…, value, earlier value, change[, change %]), computed by hand
        "headers": build_headers(form, layer),
        "rows": [format_row(tuple(row), form, layer) for row in rows],
    }


def readable_json(answers: dict[str, dict[str, Any]]) -> str:
    """JSON with one table row per line, so a person can read and review it in git."""

    def dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    blocks = []
    for case_id, answer in answers.items():
        if "error" in answer or "route" in answer:
            blocks.append(f"  {dump(case_id)}: {dump(answer)}")
            continue
        rows = ",\n".join(f"      {dump(row)}" for row in answer["rows"])
        blocks.append(
            f'  {dump(case_id)}: {{\n    "headers": {dump(answer["headers"])},\n'
            f'    "rows": [\n{rows}\n    ]\n  }}'
        )
    return "{\n" + ",\n".join(blocks) + "\n}\n"


def main() -> None:
    layer = load()
    cases = load_cases()

    def run(form: StructuredRequest) -> QueryResult:  # for the metadata facts
        return answer_request(form, layer)

    first_month, last_month = find_data_span(run)
    facts = DataFacts(first_month, last_month, find_data_date(layer, run))
    with psycopg.connect(get_settings().postgres_conninfo("query")) as conn:
        conn.execute("SET search_path TO business")
        answers = {case.id: expected_answer(case, layer, conn, facts) for case in cases.cases}
    RESULTS_FILE.write_text(readable_json(answers), encoding="utf-8")
    print(f"Wrote {len(answers)} expected answers to {RESULTS_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
