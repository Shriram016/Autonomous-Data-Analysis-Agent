"""
check_trace_fields.py — Verifies B1a instrumentation on a few REAL pipeline runs.

Runs the first 3 eval cases (calls the Groq API, costs a tiny amount) and
confirms each eval record carries the plan and a per-step trace with the
critic_check / critic_reason fields. Saves nothing to eval/results.
Run from the project root:

    python dev_checks/check_trace_fields.py
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.run_eval import run_eval
from eval.test_cases import TEST_CASES

records = run_eval(verbose=False, cases=TEST_CASES[:3])

ok = True
checked = 0
for r in records:
    plan, trace = r["plan"], r["trace"]
    has_fields = all("critic_check" in t and "critic_reason" in t for t in trace)
    print(f"\n{r['id']}: {r['query']}")
    print(f"  plan  : {' -> '.join(s['tool'] for s in plan) or '(none)'}")
    for t in trace:
        print(f"  step {t['step']} {t['tool']:<20} critic={t['critic']} "
              f"check={t['critic_check']} reason={t['critic_reason']}")
    json.dumps(r, default=str)  # must be serialisable
    if not plan:
        # Pipeline produced no plan (API error / unsolvable): nothing to instrument.
        print(f"  status={r['pipeline_status']} message={r['pipeline_message']!r}")
        print("  -> SKIPPED (no plan produced)")
        continue
    checked += 1
    good = bool(trace) and has_fields
    print(f"  -> {'PASS' if good else 'FAIL'}")
    ok &= good

ok &= checked > 0  # at least one case must have produced a plan to verify
print(f"\n{checked} case(s) checked.", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
