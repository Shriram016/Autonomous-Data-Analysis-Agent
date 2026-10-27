"""The readable eval report: one saved run (JSON) → a Markdown file next to it (M2 step 5).

The JSON is for code (compare runs, recompute); this file is for a person. For each case,
the right answer and ADAA's answer side by side: route, plan, table, and the sentence, with
pass / fail and the reason. Failures come first, so the cases to look at are on top.

Free (no LLM call): it only reads the JSON. run.py writes it after every run; to rebuild it
for an older run, from backend/:
    uv run python -m adaa.evals.report ../eval/results/2026-10-26_181933.json
"""

import json
import sys
from pathlib import Path
from typing import Any

from adaa.agent.state import Table
from adaa.evals.run import CaseResult, RunReport
from adaa.semantic_layer.request import StructuredRequest

MAX_ROWS = 10  # per table in the report; the JSON keeps every row


def cell(value: Any) -> str:
    """One Markdown table cell: no line breaks, no column breaks."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def plan(form: StructuredRequest | None) -> str:
    """The plan in one line, only the fields that were set."""
    if form is None:
        return "—"
    return "`" + json.dumps(form.model_dump(mode="json", exclude_defaults=True)) + "`"


def table_lines(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(cell(h) for h in headers) + " |",
        "|" + "---|" * len(headers),
    ]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows[:MAX_ROWS]]
    if len(rows) > MAX_ROWS:
        lines.append(f"\n…and {len(rows) - MAX_ROWS} more rows ({len(rows)} in all)")
    return lines


def expected_lines(answer: dict[str, Any]) -> list[str]:
    """The right answer: a hand-written SQL table, a must-stop error, or a quick reply."""
    if "headers" in answer:
        return table_lines(answer["headers"], answer["rows"])
    if "error" in answer:
        return [f"Must stop: `{answer['error']}`"]
    return ["`" + json.dumps(answer, ensure_ascii=False) + "`" if answer else "—"]


def adaa_lines(table: Table | None) -> list[str]:
    return table_lines(table.headers, table.rows) if table else ["No table."]


def case_lines(r: CaseResult) -> list[str]:
    mark = "PASS" if r.passed else "FAIL"
    lines = [
        f"### {mark} · `{r.id}` ({r.kind}) — {cell(r.reason)}",
        "",
        f"**Question:** {r.question}",
        "",
        "| | Expected | ADAA |",
        "|---|---|---|",
        f"| Route | {r.expected_route} | {r.route or '—'} ({r.route_source or '—'}) |",
        f"| Plan | {cell(plan(r.expected_form))} | {cell(plan(r.form))} |",
        "",
        "**Expected answer:**",
        "",
        *expected_lines(r.expected_answer),
        "",
        "**ADAA's table:**",
        "",
        *adaa_lines(r.table),
        "",
        f"**ADAA's answer:** {r.answer_text}" + (" *(template answer)*" if r.used_template else ""),
    ]
    lines += [f"- hint: {hint}" for hint in r.form_hints]
    if r.suggestions:
        lines.append("- suggestions: " + " · ".join(r.suggestions))
    lines += [f"- suggestion not answered: {s}" for s in r.unanswered_suggestions]
    lines += ["", f"${r.cost_usd:.4f} · {r.seconds:.1f} s · cache read {r.cache_read_tokens}", ""]
    return lines


def render(report: RunReport) -> str:
    share = report.passed / report.total if report.total else 0
    cache_hits = sum(r.cache_read_tokens > 0 for r in report.results)
    lines = [
        f"# Eval run {report.started_at:%Y-%m-%d %H:%M} UTC",
        "",
        f"**Score: {report.passed} / {report.total} ({share:.0%})** · cases v"
        f"{report.cases_version} · route accuracy {report.route_accuracy} · suggestions "
        f"answered {report.suggestions_answered} · template answers {report.template_answers}",
        "",
        f"Cost ${report.cost_usd:.4f} · time p50 {report.p50_seconds:.1f} s, p95 "
        f"{report.p95_seconds:.1f} s · cache reads in {cache_hits} / {report.total} questions",
        "",
        "By kind: " + ", ".join(f"{kind} {score}" for kind, score in report.by_kind.items()),
        "",
        "Router: " + ", ".join(f"{k} {v}" for k, v in report.router_sources.items()),
        "",
        "Models: " + ", ".join(f"{job} = {model}" for job, model in report.models.items()),
        "",
        "Versions: " + ", ".join(f"{k} {v}" for k, v in report.versions.model_dump().items()),
        "",
    ]
    failed = [r for r in report.results if not r.passed]
    passed = [r for r in report.results if r.passed]
    for title, group in ((f"Failed ({len(failed)})", failed), (f"Passed ({len(passed)})", passed)):
        lines += [f"## {title}", ""]
        for r in group:
            lines += case_lines(r)
    return "\n".join(lines).rstrip() + "\n"


def write_report(run_file: Path) -> Path:
    """Write <run>.md next to <run>.json and return its path."""
    report = RunReport.model_validate_json(run_file.read_text(encoding="utf-8"))
    path = run_file.with_suffix(".md")
    path.write_text(render(report), encoding="utf-8")
    return path


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m adaa.evals.report <eval/results/RUN.json>")
    print(f"Wrote {write_report(Path(sys.argv[1]))}")


if __name__ == "__main__":
    main()
