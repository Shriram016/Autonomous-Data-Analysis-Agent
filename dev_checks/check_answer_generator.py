"""
check_answer_generator.py — Sanity run for the M4 answer-model change (gpt-oss-20b).

Runs a few REAL queries (calls Groq; paced to stay under low rate limits) and
confirms that the answer is written by the LLM, not the deterministic fallback,
and that its numbers pass the B2 check. Saves nothing to eval/results. Run from
the project root:

    python dev_checks/check_answer_generator.py
"""

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.run_eval import run_eval
from eval.test_cases import TEST_CASES

ok = True
for i in (0, 10, 19, 28):  # single value, top-5 table, time ranking, shipping-time case
    rec = run_eval(verbose=False, cases=[TEST_CASES[i]])[0]
    ans_calls = [c for c in rec["llm_calls"] if c["name"] == "answer_gen"]
    llm_ok = bool(ans_calls) and ans_calls[-1]["error"] is None and not rec["answer_is_fallback"]
    num_ok = rec["answer_check"] in ("pass", "no_numbers")
    print(f"\n{rec['id']}: {rec['query']}")
    print(f"  answer     : {rec['answer']!r}")
    print(f"  answer call: {[(c['model'], c['input_tokens'], c['output_tokens'], c['latency_s'], c['error']) for c in ans_calls]}")
    print(f"  LLM-written={llm_ok}  number-check={rec['answer_check']} "
          f"unsupported={rec['answer_numbers_unsupported']}  cost=${rec['cost_usd']:.6f}")
    ok &= llm_ok and num_ok
    time.sleep(20)  # stay under the tokens-per-minute limit

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
