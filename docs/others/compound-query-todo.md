# Compound / Dual-Intent Query Handling — TODO (V2 §4)

> **Context:** Read [docs/v2-plan.md](v2-plan.md) §4 for background.
> A compound query asks for two distinct analytical results in one sentence
> (e.g. "What is the overall average shipping time? Are certain categories faster?").
> The pipeline produces one DataFrame — it cannot satisfy both intents.
> Today the planner's `unsolvable` judgment is non-deterministic on these queries.
>
> **Chosen approach: reject by design (Option A).**
> Add a compound-query detection rule to the planner prompt so the same query
> always returns `status: unsolvable` with a clear user message.
> No new tools, no state-schema changes.

---

## Prerequisites

- [x] Run `python run_tests.py` — record Test 3 baseline behavior before changes
- [x] Confirm `src/prompts/versions/v2_system_prompt.txt` is the active prompt
      (`ACTIVE_VERSION = "v2"` in `src/prompts/planner_prompt.py`)

---

## Step 1: Add Compound-Query Rule to Planner System Prompt

File: `src/prompts/versions/v2_system_prompt.txt`

- [x] Add a new rule under the existing RULES section — suggested heading:
      `### Compound / dual-intent queries`
- [x] Rule text (exact wording matters — the LLM reads this verbatim):
      "If the query asks for **two or more distinct analytical results** — for example,
      both an overall scalar AND a per-group breakdown, or two different metrics
      across two different dimensions — return `status: unsolvable` with a reason
      explaining that compound queries must be split into separate questions."
- [x] Add a counter-example immediately after the rule showing a compound query
      being rejected (mirrors the existing example style in the prompt):

      Query: "How long does shipping take? Are certain categories shipped faster?"
      → unsolvable — asks for both an overall average (scalar) AND a per-category
        breakdown (table). These are two separate questions.

- [x] Do NOT change the output schema, tool list, or any other rule.

---

## Step 2: Add `expected_status` to `EvalCase`

File: `eval/test_cases.py`

- [x] Add `expected_status: Optional[str] = None` field to the `EvalCase` dataclass
      (after `float_tol`, before `notes`)
- [x] Make `ground_truth_fn` optional: change type hint to
      `Optional[Callable[[pd.DataFrame], pd.DataFrame]]` and default to `None`
- [x] Compound eval cases will set `expected_status="unsolvable"` and
      `ground_truth_fn=None` — no DataFrame comparison needed, only status check

---

## Step 3: Update `compute_record()` in `eval/metrics.py`

File: `eval/metrics.py`

- [x] When `case.expected_status` is set (not None):
      - Override `value_match = (pipeline_result.get("status") == case.expected_status)`
      - Override `pipeline_success = value_match`
      - Set `mismatches = []` if match, else
        `[f"Expected status='{case.expected_status}', got '{pipeline_result.get('status')}'"]`
      - Skip all DataFrame comparison logic entirely (no compare_result needed)
- [x] When `case.expected_status` is None: existing logic unchanged

---

## Step 4: Update `_run_case()` in `eval/run_eval.py`

File: `eval/run_eval.py`

- [x] Before calling `case.ground_truth_fn(df)`, check `if case.ground_truth_fn is None`:
      set `gt_df = None`, `gt_error = False`, skip GT computation entirely
- [x] This prevents `TypeError: 'NoneType' object is not callable` on compound cases

---

## Step 5: Add 3–5 Compound Eval Cases to `eval/test_cases.py`

File: `eval/test_cases.py`

- [x] Add all 5 cases with `tags=["compound", "unsolvable"]`
- [x] Add to `TEST_CASES` list at the bottom (after Q30)

---

## Step 6: Dev Check

File: `dev_checks/check_compound.py` (new)

- [x] Run 3 compound queries through `run_pipeline()` directly (no eval framework)
- [x] Assert each returns `status == "unsolvable"`
- [x] Print the `reason` field so it can be reviewed for quality
- [x] Run: `python dev_checks/check_compound.py` — all 3 PASS

---

## Step 7: Verify

- [x] `python run_tests.py` — Test 3 now consistently returns `unsolvable`
- [x] `python eval/run_eval.py` — Q01–Q30 no regression; Q31–Q35 all PASS
- [x] Reason text in Q31–Q35 results is user-friendly

---

## Files Changed

| Action | File |
|---|---|
| **Updated** | `src/prompts/versions/v2_system_prompt.txt` — compound-query rule + example |
| **Updated** | `eval/test_cases.py` — `expected_status` field on `EvalCase`; 5 new cases Q31–Q35; Q31 changed to a query not present in the prompt counter-example (avoids data contamination) |
| **Updated** | `eval/metrics.py` — `compute_record()` handles `expected_status` override; report formatter handles `None` compare_mode |
| **Updated** | `eval/run_eval.py` — skip GT when `ground_truth_fn is None` |
| **New** | `dev_checks/check_compound.py` — standalone verification script |
| **Unchanged** | `eval/comparator.py`, `eval/multiturn_test_cases.py`, `eval/run_multiturn_eval.py`, all `src/core/*.py`, `src/tools/*.py` |
