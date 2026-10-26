"""Run the eval: every case through the agent, scored, printed, saved (§0 M1.7).

Each question goes through ask() directly — the eval measures the agent's quality; the queue
and the API have their own checks. Every run is saved as eval/results/<UTC date-time>.json
with the versions that produced it (models, prompts, semantic layer), so runs can be
compared over time: "the new prompt moved the score from 18/20 to 20/20".

Route cases (M2 step 2d): every case checks the route first; the report adds the route
accuracy and which router answered (Jev or Haiku). Each clarify / refuse suggestion is
then asked through the agent too, and "suggestions answered" is reported (not scored).

Costs money (~$0.04 for 44 questions and their suggestions). Runs only by hand.
Run from backend/:  uv run python -m adaa.evals.run
"""

import json
import math
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from adaa.agent.context import AgentContext, get_context
from adaa.agent.graph import ask
from adaa.agent.state import FinishedAnswer, Versions
from adaa.evals.cases import EvalSet, load_cases
from adaa.evals.expected import RESULTS_FILE
from adaa.evals.scoring import score_case
from adaa.llm.config import get_config
from adaa.settings import REPO_ROOT

RUNS_DIR = REPO_ROOT / "eval" / "results"

Ask = Callable[[str, AgentContext], FinishedAnswer]


class CaseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: str
    question: str
    route: str | None  # the route the router picked
    route_source: str | None  # the router job that answered (route_jev, route_haiku, default)
    passed: bool
    reason: str
    form_hints: list[str]
    used_template: bool  # the answer LLM failed or broke the number guardrail
    answer_text: str
    suggestions: list[str] = []  # clarify / refuse / off_topic buttons
    unanswered_suggestions: list[str] = []  # suggestions that got no table when asked
    cost_usd: float
    seconds: float


class RunReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    started_at: datetime
    cases_version: int
    models: dict[str, str]  # job → model
    versions: Versions  # semantic layer and prompts (version + fingerprint)
    passed: int
    total: int
    by_kind: dict[str, str]  # "breakdown" → "3/3"
    template_answers: int
    route_accuracy: str  # "43/44": the router picked the expected route
    router_sources: dict[str, int]  # route_jev / route_haiku / default → questions
    suggestions_answered: str  # "8/9": clarify / refuse suggestions that got a table
    cost_usd: float  # the questions and the suggestion checks
    p50_seconds: float
    p95_seconds: float
    results: list[CaseResult]


def percentile(values: list[float], share: float) -> float:
    """Nearest-rank percentile: p95 of 20 values is the 19th smallest."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)] if ordered else 0.0


def run_eval(
    context: AgentContext,
    cases: EvalSet,
    expected: dict[str, dict[str, Any]],
    ask_fn: Ask = ask,
) -> RunReport:
    started_at = datetime.now(UTC)
    results = []
    checked = answered = 0
    for case in cases.cases:
        started = time.monotonic()
        answer = ask_fn(case.question, context)
        seconds = time.monotonic() - started
        score = score_case(case, expected[case.id], answer, answer.form)
        cost = answer.usage.cost_usd
        unanswered = []
        if answer.route in ("clarify", "refuse"):  # the LLM wrote these: do they work?
            for suggestion in answer.suggestions:
                followed = ask_fn(suggestion, context)
                cost += followed.usage.cost_usd
                checked += 1
                if followed.status == "answered" and followed.table is not None:
                    answered += 1
                else:
                    unanswered.append(suggestion)
        results.append(
            CaseResult(
                id=case.id,
                kind=case.kind,
                question=case.question,
                route=answer.route,
                route_source=answer.route_source,
                passed=score.passed,
                reason=score.reason,
                form_hints=score.form_hints,
                used_template=answer.used_template,
                answer_text=answer.text,
                suggestions=answer.suggestions,
                unanswered_suggestions=unanswered,
                cost_usd=cost,
                seconds=round(seconds, 2),
            )
        )

    tally: dict[str, list[bool]] = defaultdict(list)
    for result in results:
        tally[result.kind].append(result.passed)
    config = get_config()
    times = [r.seconds for r in results]
    return RunReport(
        started_at=started_at,
        cases_version=cases.version,
        models={
            job: config.job_settings(job).model_name
            for job in (*config.router.order, "agent", "answer", "reply")
        },
        versions=context.versions,
        passed=sum(r.passed for r in results),
        total=len(results),
        by_kind={kind: f"{sum(ok)}/{len(ok)}" for kind, ok in tally.items()},
        template_answers=sum(r.used_template for r in results),
        route_accuracy=f"{sum(not r.reason.startswith('expected route') for r in results)}"
        f"/{len(results)}",
        router_sources=dict(Counter(r.route_source or "none" for r in results)),
        suggestions_answered=f"{answered}/{checked}",
        cost_usd=round(sum(r.cost_usd for r in results), 6),
        p50_seconds=percentile(times, 0.50),
        p95_seconds=percentile(times, 0.95),
        results=results,
    )


def print_report(report: RunReport) -> None:
    for r in report.results:
        mark = "PASS" if r.passed else "FAIL"
        template = "  (template answer)" if r.used_template else ""
        print(f"{mark}  {r.id:24} {r.reason:40} ${r.cost_usd:.4f}  {r.seconds:4.1f}s{template}")
        for hint in r.form_hints:
            print(f"      hint: {hint}")
        for suggestion in r.unanswered_suggestions:
            print(f"      suggestion not answered: {suggestion}")
    share = report.passed / report.total if report.total else 0
    print(f"\nScore: {report.passed} / {report.total} ({share:.0%})")
    print("By kind: " + ", ".join(f"{kind} {score}" for kind, score in report.by_kind.items()))
    print(
        f"Template answers: {report.template_answers}     Cost: ${report.cost_usd:.4f}     "
        f"Time p50 {report.p50_seconds:.1f}s, p95 {report.p95_seconds:.1f}s"
    )
    print(
        f"Route accuracy: {report.route_accuracy}     Router: {report.router_sources}     "
        f"Suggestions answered: {report.suggestions_answered}"
    )
    print(f"Models: {report.models}   Versions: {report.versions.model_dump()}")


def save(report: RunReport, folder: Path = RUNS_DIR) -> Path:
    path = folder / f"{report.started_at:%Y-%m-%d_%H%M%S}.json"
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    expected = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    report = run_eval(get_context(), load_cases(), expected)
    print_report(report)
    print(f"\nSaved {save(report).relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
