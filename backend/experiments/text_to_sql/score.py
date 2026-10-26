"""Score the text-to-SQL baseline and write a review file (M2 step 3, slice 3b).

Reads the saved baseline run (no LLM calls, free) and judges each answer against the RAW
result of the case's hand-written SQL, run again here as adaa_query. Our own agent's
pass / fail comes from its latest eval results file (same cases version), so both methods
are compared on the same cases and the same right answers.

How "right" is decided (the baseline names and formats its columns its own way):
1. Values are compared, not column names; the order of columns inside a row is ignored.
2. Numbers match at 2 decimals; a rate matches as 0.0677 or as 6.77 (a percent); a value
   the LLM rounded itself (ROUND(x, 1)) matches at its own number of decimals.
3. Rows match in any order, unless the question asks for a sort.
4. A comparison ("2018 vs 2017") is right when both period values appear in the answer.
5. A must-stop case is right only when the baseline said cannot_answer.
6. An SQL error, a timeout or a non-SELECT is wrong.

Run from backend/:  uv run python -m experiments.text_to_sql.score [baseline results file]
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg
from pydantic import BaseModel, ConfigDict

from adaa.evals.cases import EvalCase, load_cases
from adaa.evals.run import RUNS_DIR
from adaa.settings import REPO_ROOT, get_settings
from experiments.text_to_sql.baseline import Variant
from experiments.text_to_sql.run import RESULTS_DIR, BaselineResult, BaselineRun, JsonValue, to_json

Row = list[JsonValue]
FIRST_OF_MONTH = re.compile(r"^(\d{4}-\d{2})-01(T00:00:00)?$")
DATE_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2})T00:00:00$")
QUARTER = re.compile(r"^(\d{4})-Q([1-4])$")  # ours: 2017-Q2; the LLM's: 2017-04-01


# ---------- one value, one row, one table ----------


def as_number(value: JsonValue) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def as_text(value: JsonValue) -> str:
    """A date as 2017-03 (first of a month) or 2017-03-05; a quarter as its first month
    (2017-Q2 → 2017-04); other text as written."""
    text = str(value)
    if quarter := QUARTER.match(text):
        return f"{quarter.group(1)}-{(int(quarter.group(2)) - 1) * 3 + 1:02d}"
    if month := FIRST_OF_MONTH.match(text):
        return month.group(1)
    if day := DATE_TIME.match(text):
        return day.group(1)
    return text


def decimals(number: Decimal) -> int:
    exponent = number.as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def close(want: Decimal, got: Decimal) -> bool:
    """Counts and money exactly (at the answer's own decimals when the LLM rounded, up to 3);
    long decimals (averages, rates) within 0.01 % of the value, or half a cent."""
    if decimals(got) <= 3:
        return want.quantize(Decimal(1).scaleb(-decimals(got))) == got
    tolerance = Decimal("0.005") if abs(want) >= 1 else abs(want) * Decimal("0.0001")
    return abs(want - got) <= tolerance


def same_number(want: Decimal, got: Decimal) -> bool:
    return close(want, got) or close(want * 100, got)  # a rate as a share or as a percent


def same_value(want: JsonValue, got: JsonValue) -> bool:
    w, g = as_number(want), as_number(got)
    if w is not None and g is not None:
        return same_number(w, g)
    return as_text(want) == as_text(got)


def same_row(want: Row, got: Row) -> bool:
    """Same values, in any column order."""
    if len(want) != len(got):
        return False
    unused = list(got)
    for value in want:
        match = next((i for i, g in enumerate(unused) if same_value(value, g)), None)
        if match is None:
            return False
        unused.pop(match)
    return True


def same_rows(want: list[Row], got: list[Row], ordered: bool) -> bool:
    if len(want) != len(got):
        return False
    if ordered:
        return all(same_row(w, g) for w, g in zip(want, got, strict=True))
    unused = list(got)
    for row in want:
        match = next((i for i, g in enumerate(unused) if same_row(row, g)), None)
        if match is None:
            return False
        unused.pop(match)
    return True


def has_values(want: list[JsonValue], got: list[Row]) -> bool:
    """Every wanted value appears somewhere in the answer (comparisons)."""
    cells = [cell for row in got for cell in row]
    return all(any(same_value(w, c) for c in cells) for w in want)


# ---------- one case ----------


def judge(case: EvalCase, want: list[Row] | None, result: BaselineResult) -> tuple[bool, str]:
    if case.expected_error:  # must stop
        if result.cannot_answer:
            return True, "said cannot_answer"
        return False, f"answered instead of stopping ({case.expected_error})"
    assert case.expected_form is not None and want is not None
    if result.error:
        return False, result.error
    if result.cannot_answer:
        return False, "said cannot_answer"
    if case.expected_form.compare_to:  # ours: 1 row (now, before, change…); theirs: any shape
        periods = [value for row in want for value in row[-4:-2]] if want else []
        if want and len(want[0]) == 3:  # a rate: (now, before, change)
            periods = [value for row in want for value in row[:2]]
        return (
            (True, "both period values found")
            if has_values(periods, result.rows)
            else (
                False,
                "period values differ",
            )
        )
    ordered = case.expected_form.sort is not None
    if same_rows(want, result.rows, ordered):
        return True, "result matches"
    if len(want) != len(result.rows):
        return False, f"{len(result.rows)} rows, expected {len(want)}"
    return False, "different values"


class Verdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    variant: str
    passed: bool
    reason: str


def score_run(
    run: BaselineRun, cases: dict[str, EvalCase], want: dict[str, list[Row] | None]
) -> list[Verdict]:
    return [
        Verdict(id=r.id, variant=r.variant, passed=ok, reason=reason)
        for r in run.results
        for ok, reason in [judge(cases[r.id], want[r.id], r)]
    ]


# ---------- inputs and outputs ----------


def raw_answers(cases: list[EvalCase], conninfo: str) -> dict[str, list[Row] | None]:
    """Each answerable case's hand-written SQL, run again for its RAW values."""
    answers: dict[str, list[Row] | None] = {}
    with psycopg.connect(conninfo) as conn:
        conn.execute("SET search_path TO business")
        for case in cases:
            if case.expected_sql is None:
                answers[case.id] = None
                continue
            rows = conn.execute(case.expected_sql.encode("utf-8")).fetchall()
            answers[case.id] = [[to_json(v) for v in row] for row in rows]
    return answers


def latest(folder: Path, pattern: str = "*.json") -> Path:
    files = sorted(p for p in folder.glob(pattern) if not p.stem.endswith("_scores"))
    if not files:
        raise SystemExit(f"No results in {folder}")
    return files[-1]


def short(rows: list[Row], limit: int = 3) -> str:
    shown = "; ".join(", ".join(str(v) for v in row) for row in rows[:limit])
    return shown + (f" … ({len(rows)} rows)" if len(rows) > limit else "")


def review_markdown(
    run: BaselineRun,
    cases: dict[str, EvalCase],
    want: dict[str, list[Row] | None],
    verdicts: list[Verdict],
    ours: dict[str, bool],
) -> str:
    by_case: dict[str, dict[str, Verdict]] = {}
    for v in verdicts:
        by_case.setdefault(v.id, {})[v.variant] = v
    results = {(r.id, r.variant): r for r in run.results}

    def agrees(case_id: str) -> bool:
        return all(v.passed for v in by_case[case_id].values()) and ours.get(case_id, False)

    lines = [
        f"# Text-to-SQL baseline review — {run.started_at:%Y-%m-%d %H:%M} UTC",
        "",
        "Disagreements first. For each one decide: the baseline is wrong (a missed rule), a",
        "definition choice (what would a manager expect?), or our hand-written SQL is wrong.",
        "",
    ]
    for case_id in sorted(by_case, key=lambda c: (agrees(c), c)):
        case = cases[case_id]
        mark = "agree" if agrees(case_id) else "DISAGREE"
        lines += [f"## {case_id} — {mark}", "", f"**Question:** {case.question}", ""]
        rows = want[case_id]
        right = short(rows) if rows is not None else case.expected_error
        lines.append(f"- **Right answer (hand-written SQL):** {right}")
        lines.append(f"- **Our agent:** {'pass' if ours.get(case_id) else 'FAIL'}")
        variants: tuple[Variant, ...] = ("A", "B")
        for variant in variants:
            r, v = results[(case_id, variant)], by_case[case_id][variant]
            got = r.cannot_answer or r.error or short(r.rows)
            lines.append(
                f"- **Baseline {variant}:** {'pass' if v.passed else 'FAIL'} ({v.reason}) — {got}"
            )
        if case.expected_sql:
            lines += ["", "Our hand-written SQL:", "```sql", case.expected_sql.strip(), "```"]
        for variant in variants:
            sql = results[(case_id, variant)].sql
            if sql:
                lines += [f"Baseline {variant} SQL:", "```sql", sql.strip(), "```"]
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest(RESULTS_DIR)
    run = BaselineRun.model_validate_json(path.read_text(encoding="utf-8"))
    eval_set = load_cases()
    if eval_set.version != run.cases_version:
        raise SystemExit(
            f"The baseline used cases v{run.cases_version}; the file is v{eval_set.version}."
        )
    ours_file = latest(RUNS_DIR)
    ours_run = json.loads(ours_file.read_text(encoding="utf-8"))
    if ours_run["cases_version"] != run.cases_version:
        raise SystemExit(
            f"Our eval {ours_file.name} used another cases version: run it again first."
        )
    ours = {r["id"]: r["passed"] for r in ours_run["results"]}

    cases = {c.id: c for c in eval_set.cases}
    numbers = [c for c in eval_set.cases if c.expected_route == "numbers"]
    want = raw_answers(numbers, get_settings().postgres_conninfo("query"))
    verdicts = score_run(run, cases, want)

    total = len(numbers)
    for variant in ("A", "B"):
        passed = sum(v.passed for v in verdicts if v.variant == variant)
        print(f"Baseline {variant}: {passed} / {total}")
    print(f"Our agent:  {sum(ours[c.id] for c in numbers)} / {total}  ({ours_file.name})")
    print(f"Baseline cost: ${run.cost_usd:.4f}, p50 {run.p50_seconds:.1f}s")

    scores = path.with_name(f"{path.stem}_scores.json")
    scores.write_text(
        json.dumps([v.model_dump() for v in verdicts], indent=2) + "\n", encoding="utf-8"
    )
    review = path.with_name(f"{path.stem}_review.md")
    review.write_text(review_markdown(run, cases, want, verdicts, ours), encoding="utf-8")
    print(f"Saved {scores.relative_to(REPO_ROOT)} and {review.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
