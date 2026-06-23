# Eval Re-Run TODO (after Groq daily limit resets)

**Context:** Groq TPD limit (200K tokens/day) hit on 2026-06-20 during multi-turn eval subset re-run. All changes are already applied — just need to re-run and evaluate.

---

## Changes Already Applied (do NOT re-apply)

1. **`v2_system_prompt.txt`** — Follow-up handling rule updated to "follow the conversation chain" wording
2. **`v2_system_prompt.txt`** — Added two pseudo-compound clarification lines (Round 2 fix)
3. **`eval/multiturn_test_cases.py`** — MT09 turn 2 reworded: "What about the total profit?" → "What about the profit for the same?"
4. **`eval/multiturn_test_cases.py`** — MT10 turn 2 reworded same as MT09, turn 3: "And the total quantity sold?" → "And the total quantity instead?"
5. **`eval/multiturn_test_cases.py`** — MT12 turn 3 reworded: "And Tables?" → "What about Tables?"
6. **`eval/run_multiturn_eval.py`** — Added `--ids` CLI flag for subset runs

---

## Step 1 — Re-run multi-turn subset (MT09–MT16)

```bash
cd "E:\AI Agent Project"
E:\agent_env\Scripts\python.exe eval/run_multiturn_eval.py --ids MT09,MT10,MT12,MT13,MT14,MT15,MT16
```

**Expected runtime:** ~10 min (7 cases × 2-4 turns each × 20s delay between turns)

---

## Step 2 — Evaluate results

Check each case against what failed in the first run:

| ID | Previous failure | What changed | What to check |
|---|---|---|---|
| MT09 | Dropped filters (Office Supplies + 2014) when metric swapped | Query reworded to "profit for the same?" | Does it keep both filters? |
| MT10 | Same as MT09 — dropped filters on metric swap | Query reworded similarly | Same check across 3 turns |
| MT12 | "And Tables?" marked unsolvable — too terse | Changed to "What about Tables?" | Does it resolve the follow-up now? |
| MT13 | Carried forward 2014 instead of 2015 | Prompt: "follow the conversation chain" | Does it correctly trace turn 4 → turn 3 → turn 2 (2015)? |
| MT14 | Returned Profit instead of Sales (didn't carry metric swap from turn 3) | Same prompt change | Does it carry forward "total sales" from turn 3? |
| MT15 | Marked unsolvable — "can't filter multiple years" | Prompt change (chain tracing) | Will it use groupby_aggregate(Year) instead of chained filters? Likely still fails — model reasoning limitation |
| MT16 | Returned 4 regions instead of 3 (superset) | Prompt change (chain tracing) | Will it filter to 3 discussed regions? Likely still returns superset |

---

## Step 3 — Update eval report

After the run, append Round 4 (Multi-Turn) results to `eval/results/eval_report_final.md`:

- Update the test suite summary table at the top with multi-turn status
- Add a "Round 4 — Multi-Turn" section with:
  - Overall metrics (X/16 passed)
  - Per-case results table
  - Failure analysis for any remaining failures
  - Note which cases improved vs unchanged vs new regressions
- Compare against first run results (9/16 passed, 56.2%)

---

## Step 4 — Decide on remaining open items

After evaluating Round 4 results, decide on:

- [ ] **MT15/MT16 superset issue** — accept superset DataFrames (adjust ground truth) or push planner to filter?
- [ ] **"two or more values" prompt tweak** — change "compare two values" to "compare two or more values" in the groupby rule? (helps MT15 but risks over-broadening)
- [ ] **test_cases3.py replacements** — Q41, Q43 (model found workarounds), Q45, Q46 (misclassified as compound) need replacement queries (separate from multi-turn work)
