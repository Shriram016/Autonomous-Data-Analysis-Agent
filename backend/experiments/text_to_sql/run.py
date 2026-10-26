"""Run the text-to-SQL baseline on the eval's numbers cases and save every answer (M2 step 3).

Each numbers case (the answerable ones and the must-stop ones; quick-route cases are left out:
the baseline has no router) runs once per variant, A and B. Everything is saved raw — the
SQL or the reason it could not answer, the rows as the database returned them, the error,
the cost and the time — in backend/experiments/text_to_sql/results/<UTC date-time>.json.
Scoring (3b) reads that file, so the LLM is paid once and scoring can change for free.

Costs money (~$0.03: 37 cases x 2 variants). Runs only by hand.
Run from backend/:  uv run python -m experiments.text_to_sql.run
"""

import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from adaa.agent.notes import find_data_date
from adaa.agent.prompts import Prompt
from adaa.evals.cases import EvalSet, load_cases
from adaa.evals.run import percentile
from adaa.llm.config import get_config
from adaa.semantic_layer.definitions import load
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult, answer_request
from adaa.settings import get_settings
from experiments.text_to_sql.baseline import (
    HERE,
    BaselineAnswer,
    Variant,
    ask_baseline,
    build_prompt,
    read_columns,
)

RESULTS_DIR = HERE / "results"
JsonValue = str | int | float | None

Ask = Callable[[str, Variant, Prompt], BaselineAnswer]


def to_json(value: object) -> JsonValue:
    """A database value as JSON, without losing anything: Decimal as its exact text."""
    if value is None or isinstance(value, str | int | float):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


class BaselineResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: str
    question: str
    variant: Variant
    sql: str | None
    cannot_answer: str | None
    rows: list[list[JsonValue]]
    error: str | None
    cost_usd: float
    input_tokens: int
    seconds: float


class BaselineRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    started_at: datetime
    cases_version: int
    model: str
    prompts: dict[str, str]  # variant → "version (fingerprint)"
    cost_usd: float
    p50_seconds: float
    results: list[BaselineResult]


def run_baseline(cases: EvalSet, prompts: dict[Variant, Prompt], ask: Ask) -> BaselineRun:
    started_at = datetime.now(UTC)
    results = []
    numbers = [c for c in cases.cases if c.expected_route == "numbers"]
    for case in numbers:
        for variant, prompt in prompts.items():
            answer = ask(case.question, variant, prompt)
            results.append(
                BaselineResult(
                    id=case.id,
                    kind=case.kind,
                    question=case.question,
                    variant=variant,
                    sql=answer.sql,
                    cannot_answer=answer.cannot_answer,
                    rows=[[to_json(v) for v in row] for row in answer.rows],
                    error=answer.error,
                    cost_usd=answer.usage.cost_usd,
                    input_tokens=answer.usage.input_tokens,
                    seconds=answer.seconds,
                )
            )
    return BaselineRun(
        started_at=started_at,
        cases_version=cases.version,
        model=get_config().job_settings("text_to_sql").model_name,
        prompts={v: f"{p.version} ({p.fingerprint[:12]})" for v, p in prompts.items()},
        cost_usd=round(sum(r.cost_usd for r in results), 6),
        p50_seconds=percentile([r.seconds for r in results], 0.50),
        results=results,
    )


def save(run: BaselineRun, folder: Path = RESULTS_DIR) -> Path:
    folder.mkdir(exist_ok=True)
    path = folder / f"{run.started_at:%Y-%m-%d_%H%M%S}.json"
    path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    layer = load()
    conninfo = get_settings().postgres_conninfo("query")

    def agent_ask(form: StructuredRequest) -> QueryResult:  # only to find the data date
        return answer_request(form, layer)

    today = find_data_date(layer, agent_ask)  # the same "today" as the agent
    columns = read_columns(conninfo)
    prompts: dict[Variant, Prompt] = {v: build_prompt(v, columns, layer, today) for v in ("A", "B")}
    run = run_baseline(load_cases(), prompts, lambda q, v, p: ask_baseline(q, v, p, conninfo))
    for r in run.results:
        outcome = r.error or ("cannot_answer" if r.cannot_answer else f"{len(r.rows)} rows")
        print(f"{r.variant}  {r.id:32} {outcome:16} ${r.cost_usd:.4f}  {r.seconds:4.1f}s")
    print(f"\nCost: ${run.cost_usd:.4f}   Time p50 {run.p50_seconds:.1f}s   Model: {run.model}")
    print(f"Saved {save(run)}")


if __name__ == "__main__":
    main()
