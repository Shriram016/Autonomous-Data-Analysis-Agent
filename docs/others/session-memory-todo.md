# Session Memory — TODO (V2 §2)

> **Context:** Read [docs/session-memory.md](session-memory.md) for the full design
> (state schema change, why `session_id` is reused as the LangGraph `thread_id`, planner
> prompt change, reset mechanism, multi-turn eval plan).

---

## Prerequisites

- [x] Review `docs/session-memory.md` design — confirm no open questions before coding
- [x] Run baseline (`python run_tests.py`) to confirm starting point before changes

---

## Step 1: Add `recent_questions` to PipelineState

- [x] Add `recent_questions: list[str]` field to `src/core/state.py` (`PipelineState`)
- [x] Update `dev_checks/check_state.py` (or add a small check) to cover the new field

---

## Step 2: Planner Node Reads/Writes `recent_questions`

- [x] `planner_node` (`src/core/nodes.py`): read `state["recent_questions"]`, append the
      current `query`, trim to last 3, write back to state
- [x] Ensure trimming/order is "oldest first, most recent last" (matches prompt wording)

---

## Step 3: Update Planner Prompt

- [x] `src/prompts/planner_prompt.py` / `src/prompts/versions/v1_planner_prompt.txt`: when
      `recent_questions` (excluding current query) is non-empty, append a "Previous
      questions in this session" context block to the user prompt
- [x] No change to `PlanResponse`/`PlanStep` output schema — input-only change

---

## Step 4: Validate `thread_id` Reuse Mechanism (Plan A)

- [x] New `dev_checks/check_session_thread.py`: two sequential `graph.invoke()` calls on the
      same `thread_id`, confirm `recent_questions` is retrievable via `graph.get_state()`
      between calls AND each query's execution state (`plan`/`trace`/`current_step_index`/
      `run_id`) is independent
- [x] Confirms reusing `thread_id` across queries doesn't break per-query crash-recovery
      semantics (Step 7/9, frozen) — resolves the open question from the rejected
      caller-threaded approach

---

## Step 5: Update `run_pipeline()` Entry Point

- [x] `src/core/pipeline.py`: `run_pipeline(query, session_id=None)`
- [x] Use `session_id` as `thread_id` in
      `config={"configurable": {"thread_id": session_id}, ...}` — if `session_id` is `None`,
      generate one (e.g. first-ever call without a session, dev_checks)
- [x] Before `graph.invoke()`, call `graph.get_state(config)` to read the previous
      checkpoint's `recent_questions` (handle no-prior-checkpoint case → `[]`)
- [x] Feed retrieved `recent_questions` into `initial_state`
- [x] `run_id` stays as its own fresh UUID per query — for logging/tracing only, no longer
      doubles as `thread_id`
- [x] Return `session_id` and `final_state["recent_questions"]` in `_make_response()` (for
      caller visibility/debugging)

---

## Step 6: Update `app.py` (Streamlit UI)

- [x] Generate `st.session_state.session_id` (UUID) on first run, separate from per-query
      `run_id`
- [x] Pass `st.session_state.session_id` into `run_pipeline()`
- [x] Add a "New Session" button (sidebar) that opens a confirmation dialog; on confirm,
      regenerates `session_id` AND clears `st.session_state.history`/`current_result`
- [x] (Optional) Small UI indicator showing the active session's recent questions, for
      debugging/demo purposes

---

## Step 7: Multi-Turn Eval

- [x] New `eval/multiturn_test_cases.py` — `MultiTurnEvalCase` dataclass + 5-10 cases, each
      an ordered list of `(query, ground_truth_fn, compare_mode)` turns where a later turn
      is ambiguous without earlier context
- [x] New `eval/run_multiturn_eval.py` — for each case, generates one `session_id` and calls
      `run_pipeline(turn.query, session_id=session_id)` for each turn in order (checkpoint
      under `session_id` carries `recent_questions` forward automatically), compares only
      the final turn's result against its ground truth
- [x] Reuse `eval/comparator.py` / `eval/metrics.py` as-is — do not modify
      `eval/test_cases.py` or `eval/run_eval.py`

---

## Step 8: Verify

- [x] `python run_tests.py` — confirm no regression (existing single-query behavior
      unaffected — `run_pipeline()` without a `session_id` still works)
      Result: 4/5 passed (Test 3 compound-intent unsolvable is pre-existing, unrelated to session memory)
- [x] `python eval/run_multiturn_eval.py` — confirm multi-turn cases resolve follow-ups
      correctly using `recent_questions` context
      Result: 10/12 passed (83.3%). MT09 drops year filter on metric-swap; MT12 unsolvable on 3rd sub-category turn. Both are planner limitations, not session memory bugs. All 3-turn chains (MT02/04/06/08/10) pass.
- [x] Manual Streamlit UI test: ask a question, then a follow-up that depends on it,
      confirm the planner resolves it correctly; test "New Session" button clears context.
      Result: Task A ✅ — "What about 2015?" resolved correctly via recent_questions. Task B ✅ —
      New Session button clears history and regenerates session_id. LLM guesses correctly on
      simple follow-ups even without context (defaults to sales), but recent_questions provides
      precision when Q1 uses a non-default metric.

---

## Files Changed

| Action | File |
|---|---|
| **Updated** | `src/core/state.py` ✅, `src/core/nodes.py` ✅, `src/prompts/planner_prompt.py` (+ versioned prompt) ✅, `src/core/pipeline.py`, `app.py` |
| **New** | `dev_checks/check_session_thread.py` ✅, `eval/multiturn_test_cases.py`, `eval/run_multiturn_eval.py` |
| **Unchanged** | `src/core/graph.py`, `run_id` generation/semantics, `src/core/executor.py`, `src/critics/`, `src/tools/*.py`, `eval/test_cases.py`, `eval/run_eval.py`, `eval/comparator.py`, `eval/metrics.py` |
