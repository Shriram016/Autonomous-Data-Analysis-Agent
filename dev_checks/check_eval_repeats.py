"""
check_eval_repeats.py — Verifies B3a (the --ids / --repeats runner flags). Offline: no LLM calls.

1. Both runners expose --ids and --repeats (and the multi-turn one --turn-delay).
2. The planned B3 sample of 20 cases resolves to real cases, and covers every group.
3. The repeat tests pass.
Run from the project root:

    python dev_checks/check_eval_repeats.py
"""

import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The B3 sample: 17 single-turn cases (one or two per group) + 3 multi-turn cases (2, 3, 4 turns)
B3_SINGLE = ["Q01", "Q05", "Q06", "Q08", "Q11", "Q15", "Q17", "Q20", "Q23", "Q25", "Q27",
             "Q31", "Q36", "Q38", "Q41", "Q43", "Q46"]
B3_MULTI = ["MT03", "MT10", "MT15"]

ok = True


def check(name, cond, detail=""):
    global ok
    # flush: importing the eval runners later swaps sys.stdout and would drop buffered lines
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""), flush=True)
    ok &= bool(cond)


for script, flags in (("eval/run_eval.py", ["--ids", "--repeats"]),
                      ("eval/run_multiturn_eval.py", ["--ids", "--repeats", "--turn-delay"])):
    out = subprocess.run([sys.executable, script, "--help"], cwd=ROOT, capture_output=True, text=True).stdout
    for f in flags:
        check(f"{script} has {f}", f in out)

from eval.run_eval import select_cases
from eval.multiturn_test_cases import MULTITURN_TEST_CASES

cases = select_cases(B3_SINGLE)
check("17 single-turn ids resolve", len(cases) == 17)
mt = [c for c in MULTITURN_TEST_CASES if c.id in B3_MULTI]
check("3 multi-turn ids resolve", len(mt) == 3)
check("multi-turn sample spans 2, 3 and 4 turns", sorted(len(c.turns) for c in mt) == [2, 3, 4])

groups = {"aggregation": 0, "filter": 0, "rank": 0, "date": 0, "multi_condition": 0, "derived": 0,
          "pseudo_compound": 0, "compound": 0}
for c in cases:
    for t in c.tags:
        if t in groups:
            groups[t] += 1
print("   tag coverage in the sample:", groups)
check("every category is covered", all(v > 0 for v in groups.values()))
print(f"   runs planned: ({len(cases)} single + {len(mt)} multi-turn) x 3 repeats")

proc = subprocess.run([sys.executable, "-m", "pytest", "tests/test_eval_repeats.py", "-q"],
                      cwd=ROOT, capture_output=True, text=True)
check("repeat tests pass", proc.returncode == 0, proc.stdout[-300:])

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
