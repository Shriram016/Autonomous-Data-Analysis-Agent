"""
check_stability.py — Verifies B3b (eval/stability.py) end to end. Offline: no LLM calls.

1. Writes synthetic repeat-run result files (single-turn and multi-turn) covering a
   reliable query, a flaky one, a broken one, an API-error loss and a plan that changes,
   runs the real CLI on them and prints the report so you can see what it looks like.
2. Runs the CLI on a saved real result file (one repeat, older format) to confirm
   older files still work.
Run from the project root:

    python dev_checks/check_stability.py
"""

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PLAN = [{"step": 1, "tool": "aggregate_column", "input": "original_df", "output": "o",
         "parameters": {"col_name": "Sales", "operation": "sum", "new_col_name": "Sales_sum"}}]
PLAN2 = [{"step": 1, "tool": "groupby_aggregate", "input": "original_df", "output": "o",
          "parameters": {"group_col": "Region", "agg_col": {"Sales": "sum"}}}]


def r(qid, rep, passed=True, plan=PLAN, answer="Total sales are $100.", mism=None, errs=()):
    return {"id": qid, "repeat": rep, "value_match": passed, "gt_error": False,
            "pipeline_message": "", "mismatches": [] if passed else [mism or "value differs"],
            "plan": plan, "pipeline_data": [{"v": 100.0}], "answer": answer,
            "answer_is_fallback": False, "answer_check": "pass", "cost_usd": 0.0003,
            "duration_s": 6.0, "llm_latency_s": 1.4,
            "llm_calls": [{"name": "planner", "error": e} for e in errs]}


single = (
    [r("Q01", i) for i in (1, 2, 3)]                                              # reliable
    + [r("Q06", 1), r("Q06", 2, False), r("Q06", 3)]                              # flaky
    + [r("Q41", i, False, mism="wrong total") for i in (1, 2, 3)]                 # broken, same failure
    + [r("Q03", 1), r("Q03", 2, False, errs=["APITimeoutError: slow"]), r("Q03", 3)]  # one API loss
    + [r("Q36", 1, plan=PLAN), r("Q36", 2, plan=PLAN2), r("Q36", 3, plan=PLAN)]   # plan varies
)
multi = [{"id": "MT03", "repeat": i, "outcome": o, "plan": PLAN, "answer": "ok",
          "answer_check": "no_numbers", "cost_usd": 0.0012, "duration_s": 14.0,
          "llm_latency_s": 3.0, "mismatches": []} for i, o in ((1, "pass"), (2, "pass"), (3, "fail"))]

ok = True
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / "eval_demo.json").write_text(json.dumps({"aggregate": {}, "records": single}))
    (tmp / "multiturn_demo.json").write_text(json.dumps({"summary": {}, "records": multi}))
    out = tmp / "out"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "eval/stability.py"), str(tmp / "eval_demo.json"),
         str(tmp / "multiturn_demo.json"), "--out-dir", str(out)],
        capture_output=True, text=True, encoding="utf-8")
    print(proc.stdout)
    checks = {
        "CLI exits 0": proc.returncode == 0,
        "report + json saved": sorted(p.suffix for p in out.iterdir()) == [".json", ".txt"],
        "Q01 reliable": bool(re.search(r"Q01\s+3/3\s+reliable", proc.stdout)),
        "Q06 flaky": bool(re.search(r"Q06\s+2/3\s+flaky", proc.stdout)),
        "Q41 broken, same failure": "[same failure each time]" in proc.stdout,
        "Q03 API loss tagged": "[1 infra]" in proc.stdout,
        "Q36 plan change seen": "Q36" in proc.stdout and "NO" in proc.stdout,
        "multi-turn included": "MT03" in proc.stdout,
    }
    for name, cond in checks.items():
        print(f"[{'PASS' if cond else 'FAIL'}] {name}")
        ok &= cond

# Older real result file: one run per query, no plan / repeat fields
old = sorted((ROOT / "eval/results").glob("eval_2026_06_20_10_59_51.json"))
if old:
    proc = subprocess.run([sys.executable, str(ROOT / "eval/stability.py"), str(old[0]), "--no-save"],
                          capture_output=True, text=True, encoding="utf-8")
    cond = proc.returncode == 0 and "30 queries, 30 runs" in proc.stdout
    print(f"[{'PASS' if cond else 'FAIL'}] runs on an older single-repeat result file ({old[0].name})")
    ok &= cond

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
