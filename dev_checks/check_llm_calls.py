"""
check_llm_calls.py — Verifies B1c instrumentation on REAL runs and prints the
token / latency / cost numbers used for the full-eval cost estimate.

Runs 4 eval cases spread across the 30 single-turn queries (calls Groq, costs
a fraction of a cent). Saves nothing to eval/results. Run from the project root:

    python dev_checks/check_llm_calls.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.pricing import PRICES_AS_OF
from eval.run_eval import run_eval
from eval.test_cases import TEST_CASES

picked = [TEST_CASES[i] for i in (0, 9, 19, 29)]
records = run_eval(verbose=False, cases=picked)

ok = True
print(f"\nPrices as of {PRICES_AS_OF}")
print(f"{'id':<5}{'calls':>6}{'in_tok':>9}{'out_tok':>9}{'llm_s':>8}{'cost_usd':>11}  verified")
for r in records:
    print(f"{r['id']:<5}{r['llm_call_count']:>6}{r['input_tokens']:>9}{r['output_tokens']:>9}"
          f"{r['llm_latency_s']:>8}{r['cost_usd']:>11.6f}  {r['cost_all_prices_verified']}")
    for c in r["llm_calls"]:
        print(f"        - {c['name']:<11} {c['model']:<22} in={c['input_tokens']} out={c['output_tokens']} "
              f"{c['latency_s']}s err={c['error']}")
    # Every record that produced a plan must have at least a planner + answer call with tokens
    if r["plan"]:
        names = [c["name"] for c in r["llm_calls"]]
        ok &= "planner" in names and r["input_tokens"] > 0 and r["cost_usd"] > 0

n = len(records)
print(f"\nMean per query: {sum(r['input_tokens'] for r in records)/n:.0f} in-tok, "
      f"{sum(r['output_tokens'] for r in records)/n:.0f} out-tok, "
      f"${sum(r['cost_usd'] for r in records)/n:.6f}, "
      f"{sum(r['llm_latency_s'] for r in records)/n:.1f}s LLM time")
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
