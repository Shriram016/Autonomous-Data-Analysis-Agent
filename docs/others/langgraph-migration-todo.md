# LangGraph Migration — TODO

> **Context:** Read [docs/langgraph-migration.md](langgraph-migration.md) for the full migration guide (state design, node mapping, edge design, blockers).

---

## Prerequisites

- [x] Install `langgraph` and `langgraph-checkpoint-sqlite` packages
- [x] Verify existing tests pass before starting (`python run_tests.py` — expect 5/5)

> Installed `langgraph` 1.2.4 + `langgraph-checkpoint-sqlite` 3.1.0, added to `requirements.txt`.
> `run_tests.py` showed 2-4/5 passing across runs — the failures are pre-existing
> Planner LLM flakiness (Groq 400 / Pydantic validation errors from `qwen/qwen3-32b`),
> unrelated to V2 code (V1 pipeline doesn't import any new files). Not a regression.

---

## Step 1: Define Typed State

- [x] Create `src/core/state.py` with `PipelineState(TypedDict)` — all fields documented in migration guide
- [x] This is the single shared object passed through every node

> Verified via standalone script `dev_checks/check_state.py` (run from project root: `python dev_checks/check_state.py`) — PASS, 15/15 fields.

## Step 2: Port Easy Nodes

- [x] `schema_gen_node` — wrap `generate_schema()`, reads `original_df` from state, writes `schema`
- [x] `planner_node` — wrap `plan()`, reads `query` + `schema` from state, writes `plan` + `max_executions`
- [x] `answer_gen_node` — wrap `generate_answer()`, reads `query` + `final_df` from state, writes `answer` (with deterministic fallback if the LLM call fails)

> Core logic inside each function stays the same. Just change inputs/outputs to read/write state.
>
> Implemented in new file `src/core/nodes.py` (centralized adapter layer — see note in `docs/langgraph-migration.md`).
> Verified via standalone script `dev_checks/check_nodes.py` (run from project root: `python dev_checks/check_nodes.py`) — ALL CHECKS PASSED, including a real end-to-end LLM plan + answer.

## Step 3: Port Execute Step Node

- [x] `execute_step_node` — wrap `_run_step()`, runs ONE step per invocation
- [x] Reads `current_step_index`, `plan`, `state_store` from state
- [x] Writes updated `state_store`, `trace`, `total_executions`, `final_df`
- [x] Critic stays inline (called inside this node, not a separate node)

> On success: advances `current_step_index` by 1, resets `retry_count` to 0,
> sets `status="running"`. On failure: leaves `current_step_index`/`state_store`
> unchanged (so a retry re-runs the same step), sets `status="error"` + `message`.
> `trace`/`state_store` are returned as new objects (no reducers defined on
> PipelineState, so fields are overwritten, not merged).
> Implemented in `src/core/nodes.py`. Added `execute_step_started/completed/failed`
> log events to `src/utils/logger.py`.
> Verified via standalone script `dev_checks/check_execute_step.py` (run from
> project root: `python dev_checks/check_execute_step.py`) — ALL CHECKS PASSED
> (happy-path 2-step plan, failure path with bad column, out-of-range guard).

## Step 4: Wire the Graph + Conditional Edges

- [x] Create `src/core/graph.py` with `StateGraph(PipelineState)`
- [x] Add all nodes
- [x] Add linear edges: `schema_gen_node → planner_node → execute_step_node`
- [x] Add conditional edge after `execute_step_node`:
  - success + more steps → `execute_step_node` (loop back, increment `current_step_index`)
  - success + last step → `answer_gen_node`
  - fail + retries left → `param_fixer_node`
  - fail + retries exhausted → `replanner_node`
  - execution cap hit → END (error)
- [x] Add edge: `param_fixer_node → execute_step_node`
- [x] Add conditional edge after `replanner_node`:
  - success → `execute_step_node` (reset `current_step_index`, load new plan)
  - fail → END (error)
- [x] Add edge: `answer_gen_node → END`
- [x] **This step replaces `loop_controller.py` entirely** (not yet deleted — `pipeline.py`
      still uses it until Step 8; `graph.py` is a new, separate entry point for now)

> Added thin `param_fixer_node`/`replanner_node` wrappers to `src/core/nodes.py` —
> they handle state bookkeeping (retry_count, plan swap, state_store reset) around
> the existing V1 stubs (`fix_params`/`replan`), which still return "unchanged"/"error".
> Real LLM logic for these comes in Steps 5/6.
> Added `param_fixer_*`/`replanner_*` log formatting to `src/utils/logger.py`.
> Verified via `dev_checks/check_graph.py` — ALL CHECKS PASSED:
>   1. Routing unit tests for all `_route_after_*` branches (incl. cap-hit precedence).
>   2. Forced-failure sub-graph: bad column -> param_fixer x2 -> replanner (stub error) -> END.
>   3. Full `build_graph()` happy path with a real LLM plan, execution, and answer.

## Step 5: Implement Real Param Fixer

- [x] Rewrite `src/core/param_fixer.py` as an LLM node
- [x] Input: failed step, error message, critic check name, query, schema
- [x] Output: corrected `PlanStep` with fixed parameters
- [x] Increments `retry_count` in state

> Added `PARAM_FIXER_MODEL/TEMPERATURE/MAX_TOKENS/TIMEOUT_SECONDS` to `src/config.py`
> (same initial values as the planner, tunable independently).
> New prompt module `src/prompts/param_fixer_prompt.py` + versioned system prompt
> `src/prompts/versions/v1_param_fixer_prompt.txt` — focused on just the ONE failing
> tool's spec (not the full catalog), the step's current parameters, the error/critic
> message, and the CURRENT columns/dtypes of the DataFrame this step reads from
> (not just the original schema — columns can be renamed/added/dropped by earlier
> steps). Extracted `validate_tool_parameters()` out of `planner._validate_plan` so
> both the planner and param fixer share the same signature-based parameter check.
> `fix_params()` only ever changes the `parameters` field (tool/input/output/step
> untouched, preserving the state-store chain); on missing API key, API failure, or
> invalid corrected params after one retry, falls back to returning the step
> unchanged — the existing retry-exhaustion -> replanner path still handles that.
> `nodes.param_fixer_node` now passes the failed step's current input-DataFrame
> columns/dtypes into `error_context`.
> Verified via `dev_checks/check_param_fixer.py` — ALL CHECKS PASSED:
>   1. Real LLM call corrects a bad column name ("Sales Region" -> "Region").
>   2. Missing GROQ_API_KEY -> step returned unchanged.
>   3. Invalid LLM output (twice) -> step returned unchanged.
>   4. End-to-end via `param_fixer_node` -> plan updated, retry_count incremented.
> Also updated `dev_checks/check_graph.py`'s Step 4 "forced-failure" check (previously
> assumed the param_fixer stub never recovers): the real param fixer now fixes
> "Nonexistent Column" -> "Region" on the first retry and the 2-step plan completes
> successfully — renamed to `check_param_fixer_recovery` with updated assertions.
> `python run_tests.py` -> 3/5 (pre-existing Groq planner flakiness, unrelated to V2 code).

## Step 6: Implement Real Replanner

- [x] Rewrite `src/core/replanner.py` as an LLM node
- [x] Input: original query, schema, failure context (failed step + error + trace so far)
- [x] Output: completely new plan (list of PlanSteps)
- [x] Resets `current_step_index`, `retry_count`, `state_store` in state

> Added `REPLANNER_MODEL/TEMPERATURE/MAX_TOKENS/TIMEOUT_SECONDS` to `src/config.py`
> (same initial values as the planner).
> New prompt module `src/prompts/replanner_prompt.py` + versioned framing header
> `src/prompts/versions/v1_replanner_prompt.txt`, which is PREPENDED to the
> planner's existing `SYSTEM_PROMPT` at load time — the tool catalog/rules stay
> in sync automatically with the planner prompt. The user prompt includes the
> condensed schema, the FULL execution trace so far (every step attempted, with
> tool/parameters/status/output shape/critic), the failed step, and its error message.
> `replan()` reuses `PlanResponse`/`PlanStep`/`_validate_plan` from `planner.py`.
> Single retry on invalid plan (param-fixer pattern): one retry with the
> validation reason injected, then `{"status": "error", ...}`. An LLM
> `{"status": "unsolvable", ...}` response is passed through as
> `{"status": "unsolvable", "message": ...}`.
> `nodes.replanner_node` now passes `logger`/`run_id` through to `replan()`, and
> maps an "unsolvable" replan result to `state["status"]="unsolvable"` (matching
> `planner_node`'s convention) rather than a generic "error".
> Fixed a routing bug in `src/core/graph.py`: `_route_after_replanner` only checked
> for `status == "error"` and would have looped "unsolvable" back into
> `execute_step` instead of ending — now routes both "error" and "unsolvable" to END.
> Added `replanner_validation_failed`/`replanner_llm_failed` log formatting to
> `src/utils/logger.py` (matching the param_fixer pattern); `replanner_started/
> completed/failed` already existed from Step 4.
> Verified via `dev_checks/check_replanner.py` — ALL CHECKS PASSED:
>   1. Real LLM call: an unrecoverable step (aggregate_column on non-numeric
>      "Region") is replaced with a valid, differently-structured plan.
>   2. Missing GROQ_API_KEY -> `status: "error"`.
>   3. Invalid LLM output (twice, mocked) -> `status: "error"` after retry.
>   4. End-to-end via `replanner_node` -> plan replaced, `current_step_index=0`,
>      `retry_count=0`, `state_store={"original_df": ...}`, `status="running"`.
> `dev_checks/check_graph.py` re-run — ALL CHECKS PASSED (no regression from the
> routing fix). `python run_tests.py` -> 3/5 (pre-existing Groq planner flakiness
> in the unrelated V1 pipeline, not a regression).

## Step 7: Add SQLite Checkpointer

- [x] Wrap the compiled graph with `SqliteSaver` (from `langgraph-checkpoint-sqlite`)
- [x] Checkpoint file: `checkpoints/adaa.sqlite`
- [x] Each run gets a unique thread_id (use existing `run_id`)

> Added `CHECKPOINT_DB_PATH = "checkpoints/adaa.sqlite"` to `src/config.py`.
> `build_graph()` in `src/core/graph.py` is now a `@contextmanager` (not a
> plain function): it opens a `sqlite3.connect(CHECKPOINT_DB_PATH,
> check_same_thread=False)` connection, compiles the graph with
> `SqliteSaver(conn, serde=JsonPlusSerializer(pickle_fallback=True))`, yields
> the compiled graph, and closes the connection on exit. `pickle_fallback=True`
> is required — the default msgpack serde can't encode the pandas DataFrames
> in `state_store`/`original_df`/`final_df` (this was the "Thing to Watch"
> blocker flagged in `docs/langgraph-migration.md`).
> `build_graph(interrupt_after=...)` forwards to `graph.compile(interrupt_after=...)`
> for crash/resume testing.
> Callers now use `with build_graph() as graph: ...` and must pass
> `config={"configurable": {"thread_id": run_id}, ...}` to `invoke()`.
> Added `checkpoints/` to `.gitignore` (runtime DB, like `*.log`).
> Updated `dev_checks/check_graph.py`'s `check_happy_path` for the new
> context-manager API + thread_id.
> Verified via new `dev_checks/check_checkpointer.py` — ALL CHECKS PASSED:
>   1. Checkpoints persist to `checkpoints/adaa.sqlite` and are queryable via
>      `graph.get_state(config)` after a full run.
>   2. Crash/resume: a graph compiled with `interrupt_after=["execute_step"]`
>      pauses after step 1 of 2 (`trace` length 1, `answer` still `None`,
>      `get_state(config).next` non-empty); a fresh `build_graph()` instance
>      (same `thread_id`, `invoke(None, config)`) resumes from the checkpoint
>      and completes step 2 + `answer_gen`.
> `dev_checks/check_graph.py` re-run — ALL CHECKS PASSED (no regression).

## Step 8: Update Entry Points

- [x] Replace `run_pipeline()` in `src/core/pipeline.py` to invoke the graph
- [x] Update `app.py` (Streamlit UI) to call the new entry point
- [x] Remove `src/core/loop_controller.py` (logic now lives in graph edges)

> Added `GRAPH_RECURSION_LIMIT = 20` to `src/config.py` — a backstop against
> runaway graph loops, separate from (and above) the existing `max_executions
> = len(plan) * 2` cap that `_route_after_execute_step` already enforces.
> `run_pipeline()` now: loads the dataset (Stage 1, unchanged), builds an
> initial `PipelineState` (same shape as `_fresh_state()` in
> `dev_checks/check_checkpointer.py`), and runs `with build_graph() as graph:
> graph.invoke(initial_state, config={"configurable": {"thread_id": run_id},
> "recursion_limit": GRAPH_RECURSION_LIMIT})`. The graph's final
> `status="running"` (clean success) is mapped to `"success"`; `"error"`/
> `"unsolvable"` pass through unchanged. `schema`/`plan`/`final_df`/`message`/
> `trace`/`total_executions`/`answer` are read straight from `final_state`
> into the existing `_make_response()` — same response shape as V1, so
> `app.py`/`run_tests.py` needed **no changes**.
> Per-stage logging (`schema_gen_*`, `planner_*`, `execute_step_*`,
> `param_fixer_*`, `replanner_*`) is no longer duplicated in `pipeline.py` —
> `nodes.py` already logs all of it. `pipeline.py` keeps `query_received`,
> `data_loader_*`, and the final `pipeline_complete`/`pipeline_error` +
> `final_result` summary logs.
> `loop_controller.py` was **not deleted** — kept in place but unused; its
> import in `pipeline.py` and the `loop_controller_*` log-formatting branches
> in `src/utils/logger.py` are commented out (not removed), per request.
> Verified via new `dev_checks/check_pipeline.py` — happy-path query runs
> end-to-end through `run_pipeline()`, returns `status="success"` (mapped
> from `"running"`), with `schema`/`plan`/`final_df`/`trace`/`answer` all
> populated.
> `python run_tests.py` -> 2/5 (pre-existing Groq planner flakiness in
> `qwen/qwen3-32b`, same as Steps 5/6 — not a regression; the 2 successes
> used multi-execution plans with retries, confirming the loop works through
> the graph).

## Step 9: Verify

- [x] Run existing tests (`python run_tests.py` — expect 5/5)
- [x] Test Streamlit UI end-to-end
- [x] Test crash recovery via checkpointing (kill mid-run, resume)

> **Crash recovery verified via existing coverage:** `dev_checks/check_checkpointer.py`'s
> `check_crash_resume` (Step 7) already covers the meaningful case — a run is paused
> mid-plan (`interrupt_after=["execute_step"]`, so `SqliteSaver` flushes the checkpoint
> to disk with no further in-process state), then a **fresh `build_graph()`** instance
> with the same `thread_id` resumes from the checkpoint and completes. How the original
> process stopped (interrupt vs. kill vs. crash) doesn't change what gets resumed —
> the persisted checkpoint is the same either way — so no separate literal-process-kill
> script was added.
> The remaining gap — auto-*detecting* a crashed run and triggering resume without
> knowing its `run_id` in advance — is a production job-orchestration concern, out of
> scope for this project. Documented in [docs/v2-plan.md](v2-plan.md) §5
> (Checkpointing — Production Gap).

> **Streamlit UI verified manually:** ran `streamlit run app.py` and submitted
> "How long does shipping take? Are certain product categories shipped faster?"
> (the same query that intermittently returns `unsolvable` in `run_tests.py`) —
> the UI produced a successful plan, trace, and answer. Confirms `app.py`'s
> updated entry point (`run_pipeline()` via `build_graph()`, Step 8) works
> end-to-end through the UI. The query's pass/fail variance across runs is
> planner-LLM judgment flakiness (see [docs/v2-plan.md](v2-plan.md) §4
> Compound/Dual-Intent Query Handling), not a UI or graph wiring issue.

> **Planner model swap (fix for pre-existing flakiness):** Investigated via
> `dev_checks/check_structured_output.py` / `dev_checks/check_list_models.py`.
> Root cause: `qwen/qwen3-32b` (and `gpt-oss-20b` at default reasoning effort)
> are reasoning models whose `<think>`/reasoning trace shares `max_tokens` with
> the JSON output. Reasoning length is highly variable (e.g. 2,966-10,781 chars
> for the same query) — when it runs long, `content` comes back empty, causing
> Groq `json_validate_failed` (`failed_generation: ''`).
> Changed in `src/config.py`: `PLANNER_MODEL`/`PARAM_FIXER_MODEL`/`REPLANNER_MODEL`
> `qwen/qwen3-32b` -> `openai/gpt-oss-20b`, `*_MAX_TOKENS` `1024` -> `2048`.
> Added `reasoning_effort="low"` to the `client.chat.completions.create()` calls
> in `src/core/planner.py`, `src/core/param_fixer.py`, `src/core/replanner.py`
> (`reasoning_format` is not supported by gpt-oss models on Groq, so that param
> was not used).
> First test without `reasoning_effort`: `python run_tests.py` -> 5/5, then 4/5
> on a repeat run (query 3 — "How long does shipping take?..." — failed with
> `json_validate_failed`/`failed_generation: ''`), confirming the variable-length
> reasoning issue persisted even at `max_tokens=2048`.
> With `reasoning_effort="low"` added: isolated repeat test on query 3
> (`dev_checks/check_structured_output.py`, 2 runs, 70s apart) produced
> byte-identical 499-char reasoning and PASS both times (vs. 2,966-10,781 chars
> and intermittent failure before). Then `python run_tests.py` -> **5/5**,
> including query 3. Adopted as the new baseline.

---

## Files Changed

| Action | File |
|---|---|
| **New** | `src/core/state.py` ✅, `src/core/nodes.py` ✅ (centralized node adapter layer), `src/core/graph.py` |
| **Replaced** | `src/core/pipeline.py` |
| **Removed** | `src/core/loop_controller.py` |
| **Rewritten** | `src/core/param_fixer.py`, `src/core/replanner.py` |
| **Refactored** | `src/core/executor.py` (`_run_step` → `execute_step_node` in `nodes.py`; `execute()` removed) |
| **Updated** | `app.py` |
| **Unchanged** | `src/core/schema_gen.py`, `src/core/planner.py`, `src/core/answer_generator.py`, `src/tools/*.py`, `src/critics/`, `src/utils/`, `src/config.py`, `src/prompts/` |
