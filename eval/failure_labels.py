"""
failure_labels.py -- Part C: label every failure with a cause, the responsible component and
whether an automatic guardrail caught it.

Reads a finished full-eval run folder (records.jsonl, see run_full_eval.py) and writes, in that folder:
    failure_labels.json   one entry per case that has a label (evidence + confidence + guardrail info)
    failure_breakdown.csv one row per label
    failure_breakdown.txt the headline table: category x count x responsible component x caught?

Two kinds of label per case (a case can have both):
    outcome label  - why the case failed (planner, context, infrastructure ...)
    answer label   - the sentence has a number that is not in the table (answer writer), even if the
                     table was right and the case passed

Labels are assigned automatically from the saved evidence. Where the evidence is not clear-cut the
label is marked "review"; a human decision goes in eval/failure_label_overrides.json and always wins.

Usage (from project root):
    python eval/failure_labels.py eval/results/full_<timestamp>
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EVAL_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from eval.multiturn_test_cases import MULTITURN_TEST_CASES  # noqa: E402
from eval.run_full_eval import failure_kind, final_records, load_jsonl  # noqa: E402

_OVERRIDES_PATH = os.path.join(_EVAL_DIR, "failure_label_overrides.json")
_FILTER_TOOLS = {"filter_by_condition", "date_filter"}
_WINDOW_NOTE_WORDS = ("window", "synthesis", "4-turn")

# category id -> (label, responsible component)
CATEGORIES: Dict[str, tuple] = {
    "planner_missing_filter": ("Planner: missing filter", "Planner (LLM)"),
    "planner_superset_result": ("Planner: superset result (extra rows)", "Planner (LLM)"),
    "planner_wrong_step_order": ("Planner: wrong step order", "Planner (LLM)"),
    "planner_refused_answerable": ("Planner: refused an answerable query", "Planner (LLM)"),
    "planner_answered_should_refuse": ("Planner: answered a query that should be refused", "Planner (LLM)"),
    "context_loss": ("Context: earlier turn not carried forward", "Session memory / planner"),
    "planner_other_wrong_result": ("Planner: other wrong result", "Planner (LLM)"),
    "answer_wrong_number": ("Answer writer: number in the sentence is not in the table", "Answer generator (LLM)"),
    "infrastructure": ("Infrastructure: API error", "LLM provider / network"),
}


# ---------------------------------------------------------------------------
# Evidence helpers
# ---------------------------------------------------------------------------

def _tools(plan: Optional[List[Any]]) -> List[str]:
    return [(s.get("tool") if isinstance(s, dict) else s) for s in (plan or [])]


def _cells(rows: Optional[List[Dict[str, Any]]]) -> Counter:
    c: Counter = Counter()
    for row in rows or []:
        for v in row.values():
            c[round(v, 2) if isinstance(v, float) else v] += 1
    return c


def _is_superset(rec: Dict[str, Any]) -> bool:
    """The pipeline table has more rows than ground truth and contains all of ground truth's values."""
    gt, got = rec.get("gt_data"), rec.get("pipeline_data")
    if not gt or not got or len(got) <= len(gt):
        return False
    need, have = _cells(gt), _cells(got)
    return all(have[k] >= n for k, n in need.items())


def _earlier_turn_used_filter(rec: Dict[str, Any]) -> bool:
    return any(set(t.get("plan_tools") or []) & _FILTER_TOOLS for t in (rec.get("turns") or [])[:-1])


def _wrong_order(plan_tools: List[str]) -> bool:
    """A step that collapses or reshapes the table (aggregate/groupby) runs before a filter."""
    collapse = {"aggregate_column", "groupby_aggregate"}
    for i, tool in enumerate(plan_tools):
        if tool in _FILTER_TOOLS and any(t in collapse for t in plan_tools[:i]):
            return True
    return False


def guardrail_info(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Which automatic guardrails reacted during the saved run (critic, param fixer, replanner)."""
    trace = rec.get("trace") or []
    events = rec.get("events") or []
    critic = [t.get("critic_check") for t in trace if t.get("critic") == "fail"]
    fixes = sum(1 for e in events if e.get("type") == "param_fix")
    replans = sum(1 for e in events if e.get("type") == "replan")
    traced = bool(trace) or bool(events) or rec.get("outcome") != "skipped"
    return {
        "critic_fired": critic,
        "param_fix_calls": fixes,
        "replans": replans,
        "any_fired": bool(critic or fixes or replans),
        "traced": traced,
    }


# ---------------------------------------------------------------------------
# Labelling
# ---------------------------------------------------------------------------

def _label(category: str, confidence: str, evidence: List[str], dimension: str) -> Dict[str, Any]:
    return {"category": category, "label": CATEGORIES[category][0], "component": CATEGORIES[category][1],
            "confidence": confidence, "evidence": evidence, "dimension": dimension, "source": "auto"}


def label_outcome(rec: Dict[str, Any], meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Why a failed case failed. Returns None for cases that passed."""
    if rec.get("passed"):
        return None
    kind = failure_kind(rec)
    plan_tools = _tools(rec.get("plan"))
    tags = set(rec.get("tags") or meta.get("tags") or [])
    status = rec.get("pipeline_status")

    if kind == "api_error":
        return _label("infrastructure", "high", ["every failure signal is an API/network error"], "outcome")
    if kind == "refused_but_answerable":
        return _label("planner_refused_answerable", "high",
                      [f"expected an answer, planner said unsolvable: {(rec.get('pipeline_message') or '')[:120]}"],
                      "outcome")
    if kind == "answered_instead_of_refusing":
        faithful = rec.get("answer_check") in ("pass", "no_numbers")
        return _label("planner_answered_should_refuse", "high",
                      ["no ground truth exists (correct behaviour is to refuse) but the pipeline answered",
                       f"plan: {plan_tools}",
                       "answer numbers were faithful to its table" if faithful
                       else f"answer-number check: {rec.get('answer_check')}"], "outcome")

    # Everything below: an answer was expected and the result is wrong or the case could not run.
    if kind == "skipped_context_turn":
        turns = rec.get("turns") or []
        bad = next((t for t in turns if t.get("status") in ("error", "exception")), {})
        if _wrong_order(bad.get("plan_tools") or []) and "not found" in str(bad.get("message", "")):
            return _label("planner_wrong_step_order", "high",
                          [f"plan {bad.get('plan_tools')} runs a collapsing step before a filter",
                           f"tool error: {str(bad.get('message'))[:100]}"], "outcome")
        return _label("planner_other_wrong_result", "review",
                      [f"a context turn failed: {bad.get('message', 'unknown')}"[:160]], "outcome")

    # A filter dropped from a SHORT conversation is a planner failure (the filter was 1-2 turns back, well
    # inside the memory window). From 4+ turn cases a missing filter may instead be a memory failure: those
    # fall through to the context_loss label below, for review.
    short = (rec.get("num_turns") or 0) < 4
    requires_filter = bool(tags & {"filter", "multi_condition"}) or (_earlier_turn_used_filter(rec) and short)
    # A result with extra rows is a superset even when no filter step ran (checked first: it is the visible symptom)
    if requires_filter and not (set(plan_tools) & _FILTER_TOOLS) and not _is_superset(rec):
        why = ("an earlier turn filtered, the final plan has no filter step"
               if _earlier_turn_used_filter(rec) else "the question names a filter, the plan has no filter step")
        return _label("planner_missing_filter", "high",
                      [why, f"plan: {plan_tools}", f"mismatch: {str((rec.get('mismatches') or [''])[0])[:100]}"],
                      "outcome")
    if _is_superset(rec):
        return _label("planner_superset_result", "high",
                      [f"pipeline returned {len(rec['pipeline_data'])} rows, ground truth {len(rec['gt_data'])}; "
                       "all ground-truth values are present plus extras"], "outcome")
    if rec.get("kind") == "multi" and (rec.get("num_turns") or 0) >= 4:
        return _label("context_loss", "review",
                      [f"{rec['num_turns']}-turn case: the final turn depends on turns beyond the 3-question memory "
                       "window, but the planner could also simply have chosen the wrong filters",
                       f"mismatch: {str((rec.get('mismatches') or [''])[0])[:100]}"], "outcome")
    return _label("planner_other_wrong_result", "review",
                  [f"status={status}, plan: {plan_tools}", f"mismatch: {str((rec.get('mismatches') or [''])[0])[:100]}"],
                  "outcome")


def label_answer(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if rec.get("answer_check") != "fail":
        return None
    return _label("answer_wrong_number", "high",
                  [f"numbers not found in the result table or derivable from it: "
                   f"{rec.get('answer_numbers_unsupported')}",
                   "the table itself was " + ("correct" if rec.get("passed") else "not the expected one")],
                  "answer")


def load_overrides(path: str = _OVERRIDES_PATH) -> Dict[str, Any]:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def label_run(records: List[Dict[str, Any]], overrides: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Return one entry per case that has at least one label."""
    overrides = overrides or {}
    meta_by_id = {c.id: {"tags": c.tags, "notes": c.notes} for c in MULTITURN_TEST_CASES}
    out = []
    for rec in records:
        meta = meta_by_id.get(rec["id"], {})
        labels = [lbl for lbl in (label_outcome(rec, meta), label_answer(rec)) if lbl]
        ov = overrides.get(rec["id"])
        if ov:
            for lbl in labels:
                if lbl["dimension"] == "outcome" and ov.get("category") in CATEGORIES:
                    lbl.update(category=ov["category"], label=CATEGORIES[ov["category"]][0],
                               component=CATEGORIES[ov["category"]][1], confidence="reviewed", source="user_review")
                    lbl["evidence"].append(f"user review: {ov.get('note', '')}")
        if not labels:
            continue
        g = guardrail_info(rec)
        out.append({
            "id": rec["id"], "kind": rec["kind"], "repeat": rec.get("repeat", 1), "passed": rec.get("passed"),
            "labels": labels, "guardrail": g,
            "caught_by_guardrail": bool(g["any_fired"] and rec.get("passed")),
        })
    return out


def repaired_not_failures(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cases where the critic/param fixer reacted. Shown apart from the failures (Q3 default)."""
    rows = []
    for r in records:
        g = guardrail_info(r)
        if g["any_fired"]:
            rows.append({"id": r["id"], "passed": r.get("passed"), "critic_fired": g["critic_fired"],
                         "param_fix_calls": g["param_fix_calls"], "replans": g["replans"]})
    return rows


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_table(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in entries:
        for lbl in e["labels"]:
            by_cat[lbl["category"]].append({**lbl, "id": e["id"], "caught": e["caught_by_guardrail"],
                                            "fired": e["guardrail"]["any_fired"]})
    rows = []
    for cat, items in by_cat.items():
        rows.append({
            "category": CATEGORIES[cat][0], "component": CATEGORIES[cat][1], "count": len(items),
            "cases": sorted(i["id"] for i in items),
            "caught_by_production_guardrail": sum(1 for i in items if i["caught"]),
            "guardrail_fired_but_failed": sum(1 for i in items if i["fired"] and not i["caught"]),
            "review": sorted(i["id"] for i in items if i["confidence"] == "review"),
        })
    return sorted(rows, key=lambda r: -r["count"])


def render_breakdown(entries: List[Dict[str, Any]], repaired: List[Dict[str, Any]], total: int, failed: int) -> str:
    rows = build_table(entries)
    outcome = [e for e in entries if any(l["dimension"] == "outcome" for l in e["labels"])]
    lines = ["=" * 100, "FAILURE-CAUSE BREAKDOWN", "=" * 100,
             f"{failed} failed cases out of {total}; {len(entries)} cases carry a label "
             "(a passing case can still have an answer-sentence label).", "",
             f"{'Category':<58}{'Count':>6}  {'Responsible component':<26}{'Caught':>7}  Cases",
             "-" * 100]
    for r in rows:
        lines.append(f"{r['category']:<58}{r['count']:>6}  {r['component']:<26}"
                     f"{r['caught_by_production_guardrail']:>5}/{r['count']}  {', '.join(r['cases'])}")
    caught = sum(1 for e in outcome if e["caught_by_guardrail"])
    fired = sum(1 for e in outcome if e["guardrail"]["any_fired"])
    lines += ["-" * 100,
              f"'Caught' = an automatic production guardrail (critic, param fixer, replanner) reacted AND the case ended "
              f"correct. Failures caught: {caught}/{len(outcome)}. A guardrail reacted in {fired} failed case(s) but did not save it.",
              "The answer-sentence label is found only by the eval's number check, which is not part of the production pipeline.", ""]
    review = [(r["category"], r["review"]) for r in rows if r["review"]]
    if review:
        lines.append("NEEDS YOUR REVIEW (evidence not clear-cut; decide in eval/failure_label_overrides.json):")
        for cat, ids in review:
            lines.append(f"  {cat}: {', '.join(ids)}")
        lines.append("")
    lines.append("REPAIRED OR TOUCHED BY A GUARDRAIL (not counted as failures unless also listed above):")
    for r in repaired:
        lines.append(f"  {r['id']}: critic fired {r['critic_fired']}, param-fixer calls {r['param_fix_calls']}, "
                     f"replans {r['replans']} -> final result {'correct' if r['passed'] else 'still wrong'}")
    return "\n".join(lines)


def write_outputs(run_dir: str, overrides: Optional[Dict[str, Any]] = None) -> str:
    records = final_records(load_jsonl(os.path.join(run_dir, "records.jsonl")))
    # derived fields recomputed from the saved evidence, so the labels always use the current checks
    from eval.run_full_eval import recompute_derived
    records = [recompute_derived(dict(r)) for r in records]
    entries = label_run(records, overrides if overrides is not None else load_overrides())
    repaired = repaired_not_failures(records)
    failed = sum(1 for r in records if not r.get("passed"))

    with open(os.path.join(run_dir, "failure_labels.json"), "w", encoding="utf-8") as f:
        json.dump({"entries": entries, "table": build_table(entries), "repaired": repaired}, f, indent=2, default=str)
    with open(os.path.join(run_dir, "failure_breakdown.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "kind", "dimension", "category", "component", "confidence", "caught_by_guardrail",
                    "guardrail_fired", "evidence"])
        for e in entries:
            for lbl in e["labels"]:
                w.writerow([e["id"], e["kind"], lbl["dimension"], lbl["label"], lbl["component"], lbl["confidence"],
                            e["caught_by_guardrail"], e["guardrail"]["any_fired"], " | ".join(lbl["evidence"])])
    text = render_breakdown(entries, repaired, len(records), failed)
    with open(os.path.join(run_dir, "failure_breakdown.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    return text


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Label the failures of a full-eval run folder")
    parser.add_argument("run_dir", help="eval/results/full_<timestamp>")
    parser.add_argument("--overrides", default=_OVERRIDES_PATH, help="JSON file of human label decisions")
    args = parser.parse_args(argv)
    if not os.path.exists(os.path.join(args.run_dir, "records.jsonl")):
        print(f"records.jsonl not found in {args.run_dir}")
        return 2
    print(write_outputs(args.run_dir, load_overrides(args.overrides)))
    print(f"\nWrote failure_labels.json, failure_breakdown.csv and failure_breakdown.txt in {args.run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
