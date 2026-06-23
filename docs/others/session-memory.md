# Session Memory — Design (V2 §2)

## What's Changing

Today every call to `run_pipeline(query)` is fully independent — the planner sees only the
current query and the schema. V2 §2 adds short-term memory: the planner also sees the
**last 3 questions** asked in the current browser session, so follow-ups like
*"what about 2024?"* (after *"what were total sales in 2023?"*) can be resolved.

**Scope boundary (unchanged from v2-plan.md):** Questions only — not answers or DataFrames.
Each query still runs on `original_df` from scratch. No result reuse, no caching of outputs.

---

## Where `recent_questions` Lives

- `recent_questions: list[str]` is a field on `PipelineState` (`src/core/state.py`). This
  makes it part of the typed LangGraph state — `planner_node` reads it, appends the current
  query, trims to the last 3, and writes it back. It's included in each query's checkpoint
  (so it shows up in `graph.get_state()` like any other state field).
- A new `session_id` (UUID) is generated **once per browser session** in `app.py`
  (`st.session_state.session_id`, created on first run) — separate from the per-query
  `run_id`.
- `run_pipeline(query, session_id)` uses `session_id` as the LangGraph `thread_id`. Before
  invoking the graph, it calls `graph.get_state(config)` to read the *previous* checkpoint's
  `recent_questions` for that `session_id` (`[]` if no prior checkpoint — first query in the
  session), and feeds the retrieved list into `initial_state["recent_questions"]`.
- `run_id` is unchanged: still a fresh UUID per query, used for logging/tracing only — it no
  longer doubles as `thread_id`.

```
st.session_state.session_id  (created once per browser session)
        │
        ▼
run_pipeline(query, session_id)
        │
        ├─ graph.get_state({"thread_id": session_id}) ──> recent_questions (or [] if none)
        │                                                          │
        │                                                          ▼
        └─ graph.invoke(initial_state, {"thread_id": session_id})  (recent_questions fed in)
                        │
                planner_node reads recent_questions, appends query, trims to 3, writes back
                        │
                        ▼
        checkpoint for session_id now holds updated recent_questions
        (retrieved by the *next* call to run_pipeline for this session_id)
```

---

## Decision: Reusing `thread_id` as `session_id`

**Alternative considered:** keep `recent_questions` as plain data threaded by the caller
(`app.py`'s `st.session_state`), with no change to `thread_id`/`run_id`. This is simpler and
has zero interaction with the checkpointer — but it duplicates state the checkpointer already
persists (every query's final `recent_questions` is written to `checkpoints/adaa.sqlite`
regardless), and risks `st.session_state` and the checkpoint DB drifting out of sync.

**Chosen instead:** reuse a per-browser-session `session_id` (UUID, generated once in
`app.py`) as the LangGraph `thread_id`. `recent_questions` is read back via
`graph.get_state(config)` at the start of each query and written forward by `planner_node` as
part of the normal checkpoint — the checkpoint DB is the single source of truth.

**Validated in `dev_checks/check_session_thread.py`** — two sequential `graph.invoke()` calls
on the same `thread_id`, each with a full `initial_state`:
- `recent_questions` written by query 1's `planner_node` is correctly retrievable via
  `graph.get_state(config).values["recent_questions"]` before query 2 starts.
- Query 2's execution state (`plan`, `trace`, `current_step_index`, `run_id`, `status`) is
  completely independent of query 1's — reusing `thread_id` does not bleed execution state
  across queries, because every `run_pipeline()` call still passes a full `initial_state`
  (every `PipelineState` field is explicitly set, overwriting the prior checkpoint's values).
- Both queries complete cleanly (`snapshot.next == ()`) on the same `thread_id`.

**Per-query crash-recovery (Step 7/9, frozen) is unaffected**: `dev_checks/check_checkpointer.py`
uses its own freshly-generated `thread_id` (≠ `session_id`) and tests `interrupt_after`/resume
in isolation — that mechanism doesn't interact with `session_id` reuse in normal app usage,
where `build_graph()` is called without `interrupt_after` and every `graph.invoke()` runs to
completion within a single `run_pipeline()` call.

---

## State Schema Addition

```python
class PipelineState(TypedDict):
    ...
    recent_questions: list[str]   # NEW — last up-to-3 questions, oldest first
```

- `run_pipeline()` retrieves the prior value via `graph.get_state(config)` (keyed by
  `session_id` = `thread_id`) and sets `initial_state["recent_questions"]` to it (`[]` if no
  prior checkpoint exists for this `session_id` — first query in the session).
- `planner_node` appends the *current* query and trims to the last 3 before writing
  `recent_questions` back to state — so it's part of the checkpoint `graph.get_state()`
  returns for the *next* query on this `session_id`.

---

## Planner Prompt Changes

`src/prompts/planner_prompt.py` / `src/prompts/versions/v1_planner_prompt.txt`: when
`recent_questions` is non-empty (excluding the current query), append a short context block
to the user prompt, e.g.:

```
Previous questions in this session (most recent last):
1. What were total sales in 2023?

Current question: What about 2024?
```

No change to output schema (`PlanResponse`/`PlanStep`) — this only affects the prompt's
*input* context.

---

## Reset Mechanism

- **"New Session" button** in `app.py` sidebar: opens a confirmation dialog (`st.dialog`). On
  confirm, regenerates `st.session_state.session_id` (new UUID) AND clears
  `st.session_state.history` and `st.session_state.current_result` — the UI returns to its
  initial empty state. The old `session_id`'s checkpoint chain in `checkpoints/adaa.sqlite` is
  left in place (harmless orphan rows) — the next query starts on a fresh `thread_id` with no
  prior `recent_questions`. Cancel closes the dialog with no changes.
- **Page refresh**: Streamlit creates a new browser session — `st.session_state` (including
  `session_id` and `history`) resets automatically, so a new `session_id` is generated on the
  next run. This is a natural "hard reset", free of charge.

No explicit LangGraph checkpoint cleanup needed — old `session_id` checkpoint chains are
simply abandoned, not read again.

---

## Multi-Turn Eval (separate from the existing 30 cases)

`eval/test_cases.py`'s 30 `EvalCase`s are single-query (one query → one ground truth) and
stay untouched. Multi-turn cases need a different shape: a **sequence** of queries run with
shared `recent_questions`, where a later query's correctness depends on an earlier one's
context.

New, separate files (do not modify `eval/test_cases.py` / `eval/run_eval.py`):

- `eval/multiturn_test_cases.py` — defines `MultiTurnEvalCase`: an `id` + ordered list of
  `(query, ground_truth_fn, compare_mode)` turns, run sequentially with `recent_questions`
  threaded between them exactly as `app.py` would.
- `eval/run_multiturn_eval.py` — small runner: for each `MultiTurnEvalCase`, generates one
  `session_id` and calls `run_pipeline(turn.query, session_id=session_id)` for each turn in
  order — the checkpoint under that `session_id` carries `recent_questions` forward
  automatically — and compares only the **final turn's** result against its ground truth
  (earlier turns establish context).
- Target: 5-10 cases per `docs/v2-plan.md` §2, each with an unambiguous Q1 and an ambiguous
  follow-up Q2 (e.g., "what about 2024?", "and for Furniture?", "same but for the West
  region").

Reuses `eval/comparator.py` and `eval/metrics.py` as-is.

---

## Files That Will Change

| File | Change |
|---|---|
| `src/core/state.py` | Add `recent_questions: list[str]` to `PipelineState` ✅ |
| `src/core/nodes.py` | `planner_node` reads/appends/trims `recent_questions` ✅ |
| `src/prompts/planner_prompt.py` + versioned prompt | Append recent-questions context block when non-empty ✅ |
| `dev_checks/check_session_thread.py` | **New** — validates `thread_id` reuse mechanism ✅ |
| `src/core/pipeline.py` | `run_pipeline(query, session_id)` — uses `session_id` as `thread_id`, retrieves `recent_questions` via `graph.get_state()`, feeds into `initial_state` |
| `app.py` | `st.session_state.session_id` (UUID, created once); pass to `run_pipeline()`; "New Session" button regenerates `session_id` |
| `eval/multiturn_test_cases.py` | **New** — multi-turn eval cases |
| `eval/run_multiturn_eval.py` | **New** — multi-turn eval runner, threads `session_id` |

**Unchanged:** `src/core/graph.py`, `run_id` generation/semantics, checkpointing/crash-recovery
behavior (§Step 7/9), `eval/test_cases.py`, `eval/run_eval.py`, `eval/comparator.py`,
`eval/metrics.py`.
