# ADAA V2 — Upgrade Plan

## What Changed from V1

V1 used raw Python orchestration as a default, not a reasoned rejection of frameworks. V2 migrates to LangGraph because:
- Checkpointing closes the "no resumability" production gap
- Conditional edges replace manual Loop Controller logic
- Typed state replaces the raw dict state store
- Param Fixer and Replanner can become real LLM nodes instead of stubs

---

## Scope

### 1. LangGraph Migration

- [x] Migrate each pipeline component to a LangGraph node: Schema Generator, Planner, Executor, Critic, Loop Controller, Answer Generator
- [x] Replace manual Loop Controller conditional logic with LangGraph conditional edges
- [x] Replace dict state store (`{"original_df": df, "step_1_output": df, ...}`) with LangGraph typed state object passed between nodes
- [x] Add checkpointing — SQLite backend (closes V1 "no resumability" gap)
- [x] Implement real **Param Fixer** — LLM node receiving failed step + error message + critic check name + query + schema → returns corrected parameters. Replaces current stub in `src/core/param_fixer.py`.
- [x] Implement real **Replanner** — LLM node generating a completely new plan from `original_df`. Replaces current stub in `src/core/replanner.py`.

> Completed via [docs/langgraph-migration-todo.md](langgraph-migration-todo.md) Steps 1-9 (all checked).

### 2. Session Memory (Option A)

- [x] Store last 3 user questions per session in LangGraph thread state
- [x] Update Planner prompt to include prior questions as context — enables follow-up queries like "what about 2024?" after "what were 2023 sales?"
- [x] Add session reset mechanism to start a fresh conversation
- [x] Add 5–10 multi-turn eval test cases where Q2 is ambiguous without Q1 context

> **Scope boundary:** Questions only — not answers or DataFrames. Each query still runs on `original_df` from scratch. No result reuse.

> **Completed:** All items above done. Multi-turn eval: 10/12 passed (83.3%). Manual UI test confirmed. See `eval/results/pipeline_eval_report.md` for full results.

### 3. Langfuse Observability

- [x] Integrate Langfuse via native LangGraph decorator
- [x] Instrument every LLM call: Planner, Param Fixer, Replanner, Answer Generator
- [x] Nested traces: one root trace per query, one span per LangGraph node
- [x] Capture per span: prompt, response, model name, tokens, latency, cost

> Design: [docs/langfuse-observability.md](langfuse-observability.md). Step-by-step progress:
> [docs/langfuse-observability-todo.md](langfuse-observability-todo.md).

### 4. Compound / Dual-Intent Query Handling

> **Origin:** Discovered via `run_tests.py` query 3 ("How long does shipping take? Are certain product categories shipped faster?"), which intermittently returns `status: unsolvable`. The query asks for two things at different granularities — an overall scalar metric AND a per-category breakdown — in one sentence. None of the 30 `eval/test_cases.py` cases exercise this shape (all are single-intent), so the planner has no consistent example to follow and its "solvable vs unsolvable" judgment varies run to run even at `temperature=0.0`.

- [x] Decide the target behavior: reject by design (Option A) — compound queries always return `status: unsolvable`
- [x] If rejected by design: make the "unsolvable" determination deterministic (rule-based check in the prompt/validation, not LLM judgment) so the same query always returns the same verdict
- [x] Add 3-5 eval cases covering compound/dual-intent queries to `eval/test_cases.py` — Q31–Q35 added, all PASS

### 5. Checkpointing — Production Gap (documented, no implementation)

**What's built:** `build_graph()` ([src/core/graph.py](../src/core/graph.py)) compiles the graph with a `SqliteSaver` checkpointer bound to `checkpoints/adaa.sqlite` (`pickle_fallback=True` for the DataFrames in state). Every node (`schema_gen`, `planner`, `execute_step`, `param_fixer`, `replanner`, `answer_gen`) persists a full `PipelineState` snapshot after it runs, keyed by `thread_id` = `run_id`.

**What's tested:** `dev_checks/check_checkpointer.py` (Step 7) confirms checkpoints are written, and that a paused run (`interrupt_after=["execute_step"]`) can be resumed by a fresh `build_graph()` call with the same `thread_id`, completing the remaining steps.

**Does it work automatically end-to-end via the UI? No.** Two gaps:
- `run_pipeline()` generates a **new random `run_id` on every call** — no UI session is tied to a resumable `run_id`.
- Nothing detects "the previous run for this session didn't finish" and calls `invoke(None, ...)`. If the server dies mid-query, the request just fails and the user re-submits with a brand-new `run_id`, starting from scratch.

So checkpoints are written on every run, but **nothing currently reads them back** outside of the dev_checks script.

**Production approach (if deployed):**
- [ ] Move pipeline execution off the synchronous web request — submit to a background worker/task queue (Celery, RQ, or a simple DB-backed job table), returning a persistent `run_id` to the client immediately
- [ ] Use that `run_id` as the LangGraph `thread_id` (no graph change needed — already supported)
- [ ] On worker startup, scan for `run_id`s left in a non-terminal state and `invoke(None, config={"thread_id": run_id})` them — this is the "auto-resume" piece
- [ ] Client polls `/status/{run_id}` until terminal, then fetches the result
- [ ] Swap `SqliteSaver` → `PostgresSaver` (same checkpointer interface) — SQLite + concurrent workers don't mix well

> **Scope boundary:** This is real infrastructure work (task queue + job table + worker recovery loop), disproportionate to this project's single-user Streamlit scope. Documented here for awareness; not planned for implementation.

### 6. MCP — Learn Only (no implementation)

Understand what MCP is and how it is used in real production systems. No code changes to ADAA.

- [ ] Learn: what the Model Context Protocol is and the problem it solves
- [ ] Learn: how MCP servers and clients work in production
- [ ] Learn: how tools are exposed and discovered via MCP
- [ ] Learn: where MCP fits relative to LangGraph and agent frameworks

> ADAA has no implementation scope for MCP — the bounded tool registry and Pydantic validation design would conflict with an MCP client approach.

### 7. Conversation-Style UI (Chat History Display)

**Problem:** Today (`app.py`), the main area renders only `st.session_state.current_result` — a single turn. `st.session_state.history` already stores every turn (`{"query": str, "result": dict}`, newest-first), but only the latest is visible; asking a follow-up replaces the previous answer instead of appending to a conversation.

**Decided approach:**
- [x] Use Streamlit native chat elements (`st.chat_message("user")` / `st.chat_message("assistant")`, `st.chat_input()`) instead of the current `st.form` + text input
- [x] Render `st.session_state.history` oldest -> newest inside a fixed-height scrollable `st.container(height=...)` so the page doesn't grow unbounded as the conversation lengthens
- [x] Chat container shows question + answer only per turn; full detail (Result table, Execution Trace, Plan Steps) rendered outside the container for the latest turn only via `_render_details()`, overwriting on each new query
- [x] Remove the sidebar "Query History" list (redundant once all turns are visible in the chat) — keep the "Session" expander (recent questions, session ID) and "New Session" button

> Depends on Session Memory (V2 SS2, above) being complete — `recent_questions`/`session_id` plumbing is what makes a real multi-turn conversation meaningful.

### 8. Langfuse UI — Learn Only (no implementation)

Now that traces are flowing (V2 §3), learn how to actually use the Langfuse dashboard
day-to-day. No code changes to ADAA.

- [ ] Learn: how to find and open the trace for a single query (using `run_id`/`trace_id`
      printed by `dev_checks/check_langfuse.py` or logged per run)
- [ ] Learn: how to debug a single query end-to-end — drill into the root span, walk the
      nested `planner`/`param_fixer`/`replanner`/`answer_gen` generations, inspect
      prompt/response/metadata for a failing or unexpected run
- [ ] Learn: how to read token usage (`usage_details`) and cost (`cost_details`, once
      pricing is registered) per generation and aggregated per trace
- [ ] Learn: how to read latency per span/generation and spot slow nodes
- [ ] Learn: what other production metrics the Langfuse UI surfaces (e.g. traces over
      time, error rates, sessions view, scores/evals) and which would be useful to monitor
      for ADAA

### 9. Evaluation Pipeline — Final Report

End-to-end evaluation across all query types to produce a cumulative eval report with findings, failure analysis, and pipeline accuracy metrics.

- [x] Round 1 — 30 single-turn queries (Q01–Q30): 29/30 passed
- [x] Round 2 — 7 pseudo-compound queries (Q31–Q37): 4 correct, 2 partial, 1 failed
- [x] Round 3 — 10 truly compound queries (Q38–Q47): 6/10 correctly unsolvable, 2 attempted with hallucinated answers, 2 solved correctly (misclassified)
- [x] Round 4 — 16 multi-turn session memory cases (MT01–MT16): 12/16 passed (75%)
- [x] Fix misclassified compound queries (Q41, Q43, Q45, Q46) — documented in report, deferred replacement
- [x] Finalize cumulative eval report with cross-round summary

> Results and analysis: [eval/results/eval_report_final.md](../eval/results/eval_report_final.md). Re-run instructions: [docs/eval-rerun-todo.md](eval-rerun-todo.md).

---

## Metrics to Capture

| Metric | Purpose |
|---|---|
| Orchestration LOC before vs after | Show LangGraph migration impact |
| Checkpoint recovery time | Demonstrate resumability |
| Param Fixer success rate (real vs stub) | Quantify improvement over V1 |
| Replanner success rate (real vs stub) | Quantify improvement over V1 |

---

## Estimate

| Workstream | Estimate |
|---|---|
| LangGraph migration + Param Fixer + Replanner | ~2 weeks |
| Session memory | ~2 days |
| Langfuse instrumentation | ~1 day |
| MCP concepts (self-study) | ~0.5 days |
| **Total** | **~2.5–3 weeks** |

