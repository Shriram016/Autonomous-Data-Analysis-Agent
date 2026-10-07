"""
check_codegen_baseline.py — Verifies the code-writing baseline (llm_codegen_experiment/codegen_baseline.py).

Default (offline, no LLM, no cost):
  1. runs the experiment's pytest suite,
  2. sends a gallery of hostile code snippets through the REAL sandbox and shows what happened to each;
     none may succeed, none may leave a file behind.
With --live (calls the Groq API, 3 queries, about $0.001): also asks the real model to answer Q01, Q06
and Q11 and shows the code it wrote, whether it passed the safety check, and whether the answer matches
ground truth. Saves nothing.

Run from the project root:
    python llm_codegen_experiment/checks/check_codegen_baseline.py
    python llm_codegen_experiment/checks/check_codegen_baseline.py --live
"""

import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from llm_codegen_experiment import codegen_baseline as cb  # noqa: E402

HOSTILE = [
    ("read a secrets file", "result = open('.env').read()"),
    ("import os", "import os\nresult = os.listdir('.')"),
    ("__import__ trick", "result = __import__('os').listdir('.')"),
    ("dunder escape", "result = ().__class__.__bases__[0].__subclasses__()"),
    ("write a file via pandas", "df.to_csv('leak.csv')\nresult = 1"),
    ("read a file via pandas", "result = pd.read_csv('data/Sample - Superstore.csv')"),
    ("eval a string", "result = eval('1+1')"),
    ("getattr trick", "result = getattr(df, 'to_csv')('x.csv')"),
    ("environment variables", "result = os.environ"),
    ("numpy file load", "result = np.load('x.npy')"),
    ("shell via pandas io", "result = pd.io.common"),
    ("endless loop", "while True:\n    pass"),
]


def main() -> int:
    ok = True
    live = "--live" in sys.argv

    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

    proc = subprocess.run([sys.executable, "-m", "pytest", "llm_codegen_experiment/tests", "-q"], cwd=ROOT,
                          capture_output=True, text=True)
    print(f"[{'PASS' if proc.returncode == 0 else 'FAIL'}] pytest llm_codegen_experiment/tests: "
          f"{(proc.stdout.strip().splitlines() or [''])[-1]}")
    ok &= proc.returncode == 0

    df = pd.DataFrame({"Category": ["A", "B"], "Sales": [1.0, 2.0]})
    print("\nHostile snippets through the real sandbox (cwd = an empty temp folder):")
    with tempfile.TemporaryDirectory() as tmp:
        old = os.getcwd()
        os.chdir(tmp)
        try:
            for name, code in HOSTILE:
                r = cb.run_sandboxed(code, df, timeout_s=3)
                good = r["status"] in ("blocked", "error", "timeout")
                ok &= good
                print(f"  [{'PASS' if good else 'FAIL'}] {name:<26} -> {r['status']:<8} {r['message'][:70]}")
            leaked = os.listdir(tmp)
        finally:
            os.chdir(old)
        print(f"  [{'PASS' if not leaked else 'FAIL'}] no file left behind: {leaked or 'none'}")
        ok &= not leaked

    if live:
        from eval.comparator import compare
        from eval.metrics import llm_usage_summary
        from eval.run_eval import select_cases
        import eval.run_eval as run_eval_mod

        gt_df = run_eval_mod._load_dataset()
        print("\nLIVE: the real model writes code for 3 queries")
        for case in select_cases(["Q01", "Q06", "Q11"]):
            out = cb.run_codegen(case.query)
            usage = llm_usage_summary(out["llm_calls"])
            match = None
            if out["final_df"] is not None:
                match = compare(case.ground_truth_fn(gt_df), out["final_df"], case.compare_mode, case.float_tol).value_match
            print(f"\n  {case.id}: {case.query}\n    sandbox={out['sandbox_status']} matches_ground_truth={match} "
                  f"tokens={usage['input_tokens']}/{usage['output_tokens']} cost=${usage['cost_usd']:.5f}")
            print("    code: " + out["plan"][0]["parameters"]["code"].replace("\n", "\n          "))
            ok &= out["sandbox_status"] in ("ok", "blocked")  # a blocked attempt is a valid (informative) outcome

    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":      # required: the sandbox uses 'spawn', which re-imports this script
    sys.exit(main())
