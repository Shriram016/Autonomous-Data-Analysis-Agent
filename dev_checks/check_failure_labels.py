"""
check_failure_labels.py — Verifies Part C (eval/failure_labels.py) on the REAL baseline run. Free: no LLM calls.

Labels the failures of the latest eval/results/full_* folder and checks that every known case got
the expected cause, that nothing was counted as "caught", and that the output files were written.
Run from the project root:

    python dev_checks/check_failure_labels.py            # uses the latest full_* folder
    python dev_checks/check_failure_labels.py <folder>
"""

import io
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import failure_labels as fl  # noqa: E402

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

folders = sorted((ROOT / "eval/results").glob("full_*"))
run = Path(sys.argv[1]) if len(sys.argv) > 1 else (folders[-1] if folders else None)
if not run or not (run / "records.jsonl").exists():
    print("No full_* run folder with records.jsonl found. Run eval/run_full_eval.py first.")
    sys.exit(2)

# Expected cause per case in the 2026-10-06 baseline run (inspected by hand while building the labeller)
EXPECTED = {
    "Q06": "planner_missing_filter", "Q07": "planner_missing_filter",
    "MT03": "planner_missing_filter", "MT04": "planner_missing_filter",
    "MT16": "planner_superset_result",
    "MT07": "planner_wrong_step_order",
    "Q33": "planner_refused_answerable", "Q36": "planner_refused_answerable",
    "Q41": "planner_answered_should_refuse", "Q42": "planner_answered_should_refuse",
    "Q43": "planner_answered_should_refuse", "Q45": "planner_answered_should_refuse",
    "Q46": "planner_answered_should_refuse",
    "MT13": "context_loss", "MT15": "context_loss",   # 4-turn cases, flagged for review
}
ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""), flush=True)
    ok &= bool(cond)


text = fl.write_outputs(str(run), overrides={})   # no human overrides: check the automatic labels
print(text, "\n")

data = json.loads((run / "failure_labels.json").read_text(encoding="utf-8"))
outcome = {e["id"]: next(l for l in e["labels"] if l["dimension"] == "outcome")
           for e in data["entries"] if any(l["dimension"] == "outcome" for l in e["labels"])}
answer_ids = sorted(e["id"] for e in data["entries"] if any(l["dimension"] == "answer" for l in e["labels"]))

for qid, cat in EXPECTED.items():
    got = outcome.get(qid, {}).get("category")
    check(f"{qid} -> {cat}", got == cat, f"got {got}")
check("no unexpected failures labelled", set(outcome) == set(EXPECTED), f"extra: {sorted(set(outcome) - set(EXPECTED))}")
check("answer-sentence labels: Q37 and Q41", answer_ids == ["Q37", "Q41"], str(answer_ids))
check("no failure was caught by a guardrail", not any(e["caught_by_guardrail"] for e in data["entries"] if not e["passed"]))
check("MT13 and MT15 flagged for review",
      all(outcome.get(i, {}).get("confidence") == "review" for i in ("MT13", "MT15")))
for name in ("failure_labels.json", "failure_breakdown.csv", "failure_breakdown.txt"):
    check(f"{name} written", (run / name).exists())

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
