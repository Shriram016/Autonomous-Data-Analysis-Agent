"""
check_events.py — Verifies B1b instrumentation (param-fixer / replanner events).

1. Runs the deterministic fake-LLM scenarios in tests/test_events.py
   (effective fix, ineffective fixes then replan, unsolvable replan).
2. Runs ONE real query (tiny Groq call) to confirm the pipeline still works
   end to end and now returns an `events` list. A clean query has no events.
Run from the project root:

    python dev_checks/check_events.py
"""

import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

proc = subprocess.run([sys.executable, "-m", "pytest", "tests/test_events.py", "-v", "-q"],
                      cwd=ROOT, capture_output=True, text=True)
print(proc.stdout[-1500:])
ok = proc.returncode == 0

from src.core.pipeline import run_pipeline

r = run_pipeline("What is the total sales across all orders?")
print(f"real query: status={r['status']} events={r['events']}")
ok &= r["status"] == "success" and isinstance(r["events"], list)

print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
