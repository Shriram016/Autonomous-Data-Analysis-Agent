"""
check_part_a.py — Standalone verification of V2 polish Part A (hygiene, tests, CI).

Checks that the repo-hygiene files exist, requirements are pinned, .env.example
holds no real secret, the CI workflow runs pytest, and the offline test suite
passes with every API key blanked out. Run from the project root:

    python dev_checks/check_part_a.py
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


# Stray files are gone from the root; tracked homes exist
check("check_gt.py moved to dev_checks/", (ROOT / "dev_checks/check_gt.py").exists() and not (ROOT / "check_gt.py").exists())
check("eval_report_final.md moved to docs/", (ROOT / "docs/eval_report_final.md").exists() and not (ROOT / "eval_report_final.md").exists())
check("scratch notebook removed", not (ROOT / "notebooks/file1.ipynb").exists())

# Eval code is not gitignored
gitignore = (ROOT / ".gitignore").read_text()
check("eval/ is not ignored", not re.search(r"^eval/\s*$", gitignore, re.M))
for f in ("test_cases2.py", "test_cases3.py", "multiturn_test_cases.py", "run_multiturn_eval.py", "compound_test_cases.py"):
    check(f"eval/{f} exists", (ROOT / "eval" / f).exists())

# Requirements are pinned
reqs = [l.strip() for l in (ROOT / "requirements.txt").read_text().splitlines() if l.strip()]
unpinned = [l for l in reqs if "==" not in l]
check("requirements.txt fully pinned", not unpinned, f"unpinned: {unpinned}")
check("requirements-dev.txt includes pytest", "pytest==" in (ROOT / "requirements-dev.txt").read_text())

# .env.example exists and holds no real secret
env_example = (ROOT / ".env.example").read_text()
check(".env.example exists with GROQ_API_KEY", "GROQ_API_KEY=" in env_example)
check(".env.example has no real key", not re.search(r"gsk_[A-Za-z0-9]{10,}|sk-lf-|pk-lf-", env_example))

# CI workflow + README badge + clone URL
ci = (ROOT / ".github/workflows/ci.yml").read_text()
check("CI workflow runs pytest", "pytest" in ci)
readme = (ROOT / "README.md").read_text(encoding="utf-8")
check("README has CI badge", "actions/workflows/ci.yml/badge.svg" in readme)
check("README has no <repo-url> placeholder", "<repo-url>" not in readme)

# Offline suite passes with all API keys blanked (this is what CI sees)
env = {**os.environ, "GROQ_API_KEY": "", "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""}
proc = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=ROOT, env=env,
                      capture_output=True, text=True)
tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-300:]
check("pytest passes with no API keys", proc.returncode == 0, tail)
print(f"      {tail}")

print()
print("ALL CHECKS PASSED" if not failures else f"{len(failures)} CHECK(S) FAILED: {failures}")
sys.exit(1 if failures else 0)
