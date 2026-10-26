from collections import Counter
from pathlib import Path

import pytest

from adaa.evals.cases import CASES_FILE, EvalCaseError, check_cases, load_cases
from adaa.semantic_layer.definitions import load


def test_the_real_cases_load_and_every_expected_form_compiles() -> None:
    cases = load_cases()
    assert len(cases.cases) == 30  # v3: 20 from M1 + 10 from M2 step 1
    assert check_cases(cases, load()) == []


def test_every_kind_is_covered() -> None:
    kinds = Counter(case.kind for case in load_cases().cases)
    assert set(kinds) == {
        "simple",
        "breakdown",
        "period",
        "filter",
        "status",
        "relative_date",
        "top",
        "compare",
        "must_stop",
    }


def copy_with(tmp_path: Path, old: str, new: str) -> Path:
    text = CASES_FILE.read_text(encoding="utf-8")
    assert old in text, f"test setup: '{old}' not found"
    path = tmp_path / "cases.yaml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


def test_a_repeated_id_is_refused(tmp_path: Path) -> None:
    with pytest.raises(EvalCaseError, match="used twice"):
        load_cases(copy_with(tmp_path, "id: number_of_customers", "id: total_revenue"))


def test_both_or_neither_expectation_is_refused(tmp_path: Path) -> None:
    both = "    expected_error: value_not_found\n"
    path = copy_with(tmp_path, both, both + "    expected_form: {metric: revenue}\n")
    with pytest.raises(EvalCaseError, match="or expected_error alone"):
        load_cases(path)


def test_an_expected_form_that_does_not_compile_is_reported(tmp_path: Path) -> None:
    path = copy_with(
        tmp_path, "expected_form: {metric: customers}", "expected_form: {metric: buyers}"
    )
    problems = check_cases(load_cases(path), load())
    assert len(problems) == 1
    assert problems[0].startswith(
        "case 'number_of_customers': No metric called 'buyers'. Known metrics: orders, revenue,"
    )


def test_a_form_without_its_hand_written_sql_is_refused(tmp_path: Path) -> None:
    path = copy_with(
        tmp_path,
        "    expected_sql: |\n      SELECT avg(review_score) FROM reviews\n",
        "",
    )
    with pytest.raises(EvalCaseError, match="or expected_error alone"):
        load_cases(path)


def test_expected_results_cover_every_case() -> None:
    import json

    from adaa.evals.expected import RESULTS_FILE

    stored = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    assert set(stored) == {case.id for case in load_cases().cases}
    assert stored["revenue_in_paris"] == {"error": "value_not_found"}
    assert stored["total_revenue"]["rows"] == [["R$ 13,221,498.11"]]
