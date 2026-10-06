"""
check_full_eval.py — Verifies the full-eval runner (eval/run_full_eval.py) before the real 63-case run.

1. Runs the offline tests (fake pipelines: normal run, crash + resume, API-error re-run, dry run, ...).
2. Runs a REAL --dry-run in your environment (dataset, git, hashes, plan; no LLM calls) and checks the manifest.
3. With --ping: also runs the real preflight (a few tiny LLM calls to prove the key and models work)
   and answers "n" at the confirmation prompt, so nothing is run and nothing is saved.
Run from the project root:

    python dev_checks/check_full_eval.py
    python dev_checks/check_full_eval.py --ping
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""), flush=True)
    ok &= bool(cond)


proc = subprocess.run([sys.executable, "-m", "pytest", "tests/test_full_eval.py", "-q"],
                      cwd=ROOT, capture_output=True, text=True)
check("offline tests pass", proc.returncode == 0, proc.stdout[-400:])
print("      " + (proc.stdout.strip().splitlines() or [""])[-1])

with tempfile.TemporaryDirectory() as tmp:
    proc = subprocess.run([sys.executable, "eval/run_full_eval.py", "--dry-run", "--out-dir", tmp],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    print(proc.stdout)
    check("dry run exits 0", proc.returncode == 0, proc.stderr[-300:])
    folders = [p for p in Path(tmp).iterdir() if p.name.startswith("full_")]
    check("one run folder created", len(folders) == 1)
    if folders:
        m = json.loads((folders[0] / "manifest.json").read_text(encoding="utf-8"))
        check("manifest status is dry_run", m["status"] == "dry_run")
        check("git commit recorded", bool(m["git"]["commit"]), "is this a git repo?")
        check("dataset hash recorded", len(((m.get("dataset") or {}).get("sha256")) or "") == 64)
        check("models and settings recorded", bool(m["settings"].get("PLANNER_MODEL") and m["settings"].get("ANSWER_MODEL")))
        check("code and prompt hashes recorded", len(m["code_hashes"]) >= 8)
        check("plan is 47 single + 16 multi",
              m["plan"] == {"single_cases": 47, "multi_cases": 16, "runs_expected": 63}, str(m["plan"]))
        check("no records written in a dry run", not (folders[0] / "records.jsonl").exists())
        print("      uncommitted tracked files:", m["git"]["uncommitted_tracked_files"] or "none")

if "--ping" in sys.argv:
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run([sys.executable, "eval/run_full_eval.py", "--out-dir", tmp],
                              cwd=ROOT, input="n\n", capture_output=True, text=True, encoding="utf-8")
        print(proc.stdout)
        check("real preflight reaches the models", "[OK] LLM reachable" in proc.stdout, proc.stdout[-400:])
        check("answering 'n' cancels and saves nothing",
              "Cancelled" in proc.stdout and not any(Path(tmp).iterdir()))

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
