"""The readable eval report: built from a fake run, no database, no cost."""

from pathlib import Path

from adaa.agent.state import Table
from adaa.evals.report import MAX_ROWS, render, write_report
from adaa.evals.run import RunReport, save
from tests.unit.test_eval_run import report


def with_one_failure() -> RunReport:
    """The fake run, with the first case (total_revenue) turned into a failure."""
    r = report()
    first, second = r.results
    failed = first.model_copy(update={"passed": False, "reason": "result differs"})
    return r.model_copy(update={"passed": 1, "results": [failed, second]})


def test_summary_is_on_top() -> None:
    text = render(report())
    assert text.startswith("# Eval run ")
    assert "**Score: 2 / 2 (100%)**" in text and "route accuracy 2/2" in text
    assert "cache reads in 0 / 2 questions" in text


def test_failures_come_first() -> None:
    text = render(with_one_failure())
    assert text.index("## Failed (1)") < text.index("FAIL · `total_revenue`")
    assert text.index("FAIL · `total_revenue`") < text.index("## Passed (1)")
    assert text.index("## Passed (1)") < text.index("PASS · `revenue_in_paris`")


def test_each_case_shows_both_sides() -> None:
    text = render(report())
    assert "| Route | numbers | numbers (test) |" in text
    assert '| Plan | `{"metric": "revenue"}` | `{"metric": "revenue"}` |' in text
    assert text.count("| R$ 100.00 |") == 2  # the expected table and ADAA's table
    assert "**ADAA's answer:** Revenue was R$ 100.00." in text
    assert "Must stop: `value_not_found`" in text  # the must-stop case
    assert "No table." in text  # ... which has no table


def test_long_tables_are_cut_in_the_report_only() -> None:
    r = report()
    first, second = r.results
    rows = [[f"R$ {i}.00"] for i in range(MAX_ROWS + 5)]
    long = first.model_copy(update={"table": Table(headers=["Revenue"], rows=rows)})
    text = render(r.model_copy(update={"results": [long, second]}))
    assert f"| R$ {MAX_ROWS - 1}.00 |" in text and f"| R$ {MAX_ROWS}.00 |" not in text
    assert f"…and 5 more rows ({MAX_ROWS + 5} in all)" in text


def test_report_is_written_next_to_the_run(tmp_path: Path) -> None:
    run = report()
    run_file = save(run, tmp_path)
    md = write_report(run_file)
    assert md == run_file.with_suffix(".md")
    assert md.read_text(encoding="utf-8") == render(run)  # built from the saved JSON
