"""
stability.py -- B3b: how consistent is the agent across repeated runs of the same query?

Reads eval result files that contain repeat runs (records carry an `id` and a
`repeat` number; produced by `run_eval.py --repeats N` and
`run_multiturn_eval.py --repeats N`) and reports, per query:

    result stability   reliable (all runs pass) / flaky (some pass) / broken (none pass)
    plan consistency   same tools and parameters in every run?
    table consistency  same result table in every run? (single-turn only; multi-turn
                       records do not save the table)
    answer numbers     same numbers in the answer text? (wording is ignored)
    infra noise        failures caused by API errors, kept apart from real weaknesses

and overall: accuracy per repeat with its spread, plus average cost and time.

Usage (from project root):
    python eval/stability.py eval/results/eval_*.json eval/results/multiturn_*.json
"""

from __future__ import annotations

import io
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EVAL_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from eval.answer_check import extract_numbers  # noqa: E402

_RESULTS_DIR = os.path.join(_EVAL_DIR, "results")

# Errors that come from the API / network, not from the agent's own logic.
_INFRA_RE = re.compile(
    r"timed out|APITimeout|APIConnection|RateLimit|rate limit|service unavailable|"
    r"connection failed|Groq API (error|connection)|Error code: (429|5\d\d)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Per-record helpers
# ---------------------------------------------------------------------------

def _expects_refusal(rec: Dict[str, Any]) -> bool:
    """
    Single-turn cases with no ground truth (Q38-Q47 compound queries) are ones where
    the correct behaviour is to refuse ("unsolvable"): one result table cannot hold
    two different answers. The saved record shows this as gt_data == None.
    """
    if "expected_behavior" in rec:
        return rec["expected_behavior"] == "refuse"
    return "outcome" not in rec and not rec.get("gt_error") and "gt_data" in rec and rec["gt_data"] is None


def _passed(rec: Dict[str, Any]) -> bool:
    if "passed" in rec:  # newer records carry the verdict computed at run time
        return bool(rec["passed"])
    if "outcome" in rec:  # multi-turn record
        return rec["outcome"] == "pass"
    if _expects_refusal(rec):  # correct = refused; answering anyway counts as a failure
        return rec.get("pipeline_status") == "unsolvable"
    return bool(rec.get("value_match")) and not rec.get("gt_error")


def _is_infra_failure(rec: Dict[str, Any]) -> bool:
    if _passed(rec):
        return False
    texts = [str(c.get("error") or "") for c in rec.get("llm_calls") or []]
    texts.append(str(rec.get("pipeline_message") or ""))
    texts.extend(str(m) for m in rec.get("mismatches") or [])
    return any(_INFRA_RE.search(t) for t in texts)


def _failure_reason(rec: Dict[str, Any]) -> str:
    if _expects_refusal(rec):
        return f"expected a refusal but pipeline_status={rec.get('pipeline_status')}"
    mism = rec.get("mismatches") or []
    return str(mism[0]) if mism else str(rec.get("pipeline_message") or "unknown")


def _mask_new_columns(value: Any, created: Dict[str, str]) -> Any:
    """Replace names of columns the plan itself creates (and names derived from them, like
    `<name>_mean`) with stable placeholders, so an invented name such as `Order Month` vs
    `OrderMonth` does not count as a different plan."""
    if isinstance(value, str):
        for name, token in created.items():
            if value == name or value.startswith(name + "_"):
                return token + value[len(name):]
        return value
    if isinstance(value, dict):
        return {_mask_new_columns(k, created): _mask_new_columns(v, created) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_new_columns(v, created) for v in value]
    return value


def _canonical_plan(rec: Dict[str, Any]) -> Optional[str]:
    plan = rec.get("plan") or []
    if not plan:
        return None
    created: Dict[str, str] = {}
    steps = []
    for s in plan:
        params = s.get("parameters") or {}
        new_col = params.get("new_col_name")
        if isinstance(new_col, str) and new_col not in created:
            created[new_col] = f"<new{len(created) + 1}>"
        steps.append({"tool": s.get("tool"), "parameters": _mask_new_columns(params, created)})
    return json.dumps(steps, sort_keys=True, default=str)


def _round(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, dict):
        return {k: _round(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_round(x) for x in v]
    return v


def _canonical_table(rec: Dict[str, Any]) -> Optional[str]:
    """Same result table = same rows of values; column names and column order are ignored
    (the planner invents names like `shipping_time` vs `shipping_days`)."""
    data = rec.get("pipeline_data")
    if not data:
        return None
    rows = [sorted(json.dumps(_round(v), default=str) for v in row.values()) for row in data]
    return json.dumps(rows)


_LIST_MARKER_RE = re.compile(r"^[ \t]*(?:[-*]\s+)?\d+[.)]\s+", re.MULTILINE)


def _sig3(v: float) -> float:
    """Round to 3 significant digits, so $286,397.02 and $286,397 count as the same number."""
    return float(f"{v:.3g}")


def _answer_numbers(rec: Dict[str, Any]) -> Optional[frozenset]:
    """Numbers in the answer, ignoring list numbering ("1. California ...") and rounding detail."""
    answer = rec.get("answer")
    if not answer or rec.get("answer_is_fallback"):
        return None
    text = _LIST_MARKER_RE.sub("", answer)
    return frozenset(_sig3(abs(n["value"])) for n in extract_numbers(text))


def _is_chain(sets: List[frozenset]) -> bool:
    """True if every answer's numbers are contained in the next larger one (extras allowed)."""
    ordered = sorted(sets, key=len)
    return all(a <= b for a, b in zip(ordered, ordered[1:]))


def _consistent(values: List[Any]) -> Optional[bool]:
    """True/False if at least two runs have a value to compare, else None (cannot tell)."""
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return None
    return len(set(present)) == 1


def _numbers_consistent(values: List[Optional[frozenset]]) -> Optional[bool]:
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return None
    return _is_chain(present)


def _mean(xs: List[float]) -> float:
    return round(statistics.mean(xs), 6) if xs else 0.0


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def compute_stability(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_id: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_id[r["id"]].append(r)

    queries: Dict[str, Dict[str, Any]] = {}
    for qid, runs in by_id.items():
        runs = sorted(runs, key=lambda r: r.get("repeat", 1))
        passes = sum(1 for r in runs if _passed(r))
        failed = [r for r in runs if not _passed(r)]
        infra = [r for r in failed if _is_infra_failure(r)]
        real = [r for r in failed if r not in infra]

        if passes == len(runs):
            status = "reliable"
        elif passes == 0:
            status = "infra_only" if not real else "broken"
        else:
            status = "flaky"

        plans = [_canonical_plan(r) for r in runs]
        queries[qid] = {
            "runs": len(runs),
            "passes": passes,
            "status": status,
            "infra_failures": len(infra),
            "same_failure": (
                len({_failure_reason(r) for r in real}) == 1 if len(real) >= 2 else None
            ),
            "plan_consistent": _consistent(plans),
            "distinct_plans": len({p for p in plans if p is not None}),
            "table_consistent": _consistent([_canonical_table(r) for r in runs]),
            "answer_numbers_consistent": _numbers_consistent([_answer_numbers(r) for r in runs]),
            "expects_refusal": all(_expects_refusal(r) for r in runs),
            "answer_check": dict(Counter(r.get("answer_check", "n/a") for r in runs)),
            "avg_cost_usd": _mean([r.get("cost_usd") or 0.0 for r in runs]),
            "avg_duration_s": _mean([r.get("duration_s") or 0.0 for r in runs]),
            "multi_turn": any("outcome" in r for r in runs),
        }

    # Accuracy per repeat number
    per_repeat: Dict[int, List[bool]] = defaultdict(list)
    for r in records:
        per_repeat[r.get("repeat", 1)].append(_passed(r))
    repeat_accuracy = {k: round(sum(v) / len(v), 4) for k, v in sorted(per_repeat.items())}
    accs = list(repeat_accuracy.values())

    statuses = Counter(q["status"] for q in queries.values())
    plan_known = [q["plan_consistent"] for q in queries.values() if q["plan_consistent"] is not None]

    return {
        "queries": queries,
        "summary": {
            "unique_queries": len(queries),
            "total_runs": len(records),
            "repeats": sorted(per_repeat),
            "accuracy_per_repeat": repeat_accuracy,
            "accuracy_mean": round(statistics.mean(accs), 4) if accs else 0.0,
            "accuracy_min": min(accs) if accs else 0.0,
            "accuracy_max": max(accs) if accs else 0.0,
            "accuracy_std": round(statistics.pstdev(accs), 4) if len(accs) > 1 else 0.0,
            "status_counts": {k: statuses.get(k, 0) for k in ("reliable", "flaky", "broken", "infra_only")},
            "infra_failed_runs": sum(q["infra_failures"] for q in queries.values()),
            "plan_identical_share": round(sum(plan_known) / len(plan_known), 4) if plan_known else None,
            "avg_cost_usd_per_run": _mean([r.get("cost_usd") or 0.0 for r in records]),
            "avg_duration_s_per_run": _mean([r.get("duration_s") or 0.0 for r in records]),
            "avg_llm_latency_s_per_run": _mean([r.get("llm_latency_s") or 0.0 for r in records]),
        },
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _yn(v: Optional[bool]) -> str:
    return "n/a" if v is None else ("yes" if v else "NO")


def render_report(result: Dict[str, Any]) -> str:
    s = result["summary"]
    lines = [
        "=" * 78,
        "ADAA Stability Report",
        "=" * 78,
        f"{s['unique_queries']} queries, {s['total_runs']} runs, repeats observed: {s['repeats']}",
        "",
        f"{'id':<6}{'pass':>6}  {'status':<11}{'plan same':<11}{'table same':<12}"
        f"{'numbers same':<14}{'B2 check':<22}{'cost $':>9}",
        "-" * 78,
    ]
    for qid in sorted(result["queries"]):
        q = result["queries"][qid]
        b2 = ",".join(f"{k}:{v}" for k, v in sorted(q["answer_check"].items()))
        note = ""
        if q["infra_failures"]:
            note = f"  [{q['infra_failures']} infra]"
        if q.get("expects_refusal"):
            note += "  [correct = refuse]"
        if q["status"] == "broken" and q["same_failure"] is not None:
            note += "  [same failure each time]" if q["same_failure"] else "  [failure differs]"
        lines.append(
            f"{qid:<6}{q['passes']}/{q['runs']:<4}  {q['status']:<11}{_yn(q['plan_consistent']):<11}"
            f"{_yn(q['table_consistent']):<12}{_yn(q['answer_numbers_consistent']):<14}"
            f"{b2[:20]:<22}{q['avg_cost_usd']:>9.5f}{note}"
        )
    c = s["status_counts"]
    lines += [
        "-" * 78,
        f"Accuracy per repeat : {s['accuracy_per_repeat']}",
        f"Accuracy            : mean {s['accuracy_mean']:.1%}, range {s['accuracy_min']:.1%} to "
        f"{s['accuracy_max']:.1%}, std {s['accuracy_std']:.1%}",
        f"Queries             : {c['reliable']} reliable, {c['flaky']} flaky, {c['broken']} broken, "
        f"{c['infra_only']} lost to API errors",
        f"Failed runs caused by API errors (not agent weakness): {s['infra_failed_runs']}",
        "Identical plan across runs: "
        + ("n/a" if s["plan_identical_share"] is None else f"{s['plan_identical_share']:.0%} of queries"),
        f"Average per run     : ${s['avg_cost_usd_per_run']:.5f}, {s['avg_duration_s_per_run']:.1f}s total, "
        f"{s['avg_llm_latency_s_per_run']:.1f}s in LLM calls",
        "",
        "Notes: 'n/a' means there was nothing to compare (e.g. multi-turn records do not save the result table).",
        "Plans are compared ignoring column names the plan invents (e.g. Order Month vs OrderMonth); tables are",
        "compared by their cell values, ignoring column names and column order.",
        "Answer wording is ignored; only the numbers in the answer text are compared (list numbering ignored,",
        "rounded to 3 significant digits, and an answer that adds extra numbers still counts as consistent).",
        "'[correct = refuse]': no ground truth exists for this query; the right behaviour is to answer 'unsolvable'.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_records(paths: List[str]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        records.extend(data["records"] if isinstance(data, dict) else data)
    return records


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="ADAA stability report over repeated eval runs")
    parser.add_argument("files", nargs="+", help="eval result JSON files (single-turn and/or multi-turn)")
    parser.add_argument("--out-dir", default=_RESULTS_DIR, help="where to save the report")
    parser.add_argument("--no-save", action="store_true", help="print only, save nothing")
    args = parser.parse_args(argv)

    result = compute_stability(load_records(args.files))
    report = render_report(result)
    print(report)

    if not args.no_save:
        os.makedirs(args.out_dir, exist_ok=True)
        base = os.path.join(args.out_dir, f"stability_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}")
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nSaved: {base}.json / .txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
