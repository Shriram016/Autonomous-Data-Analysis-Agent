# Langfuse Observability — TODO (V2 §3)

> **Context:** Read [docs/langfuse-observability.md](langfuse-observability.md) for the full
> design (architecture, trace/session ID mapping, shared helper, per-LLM-call generation
> details).

---

## Prerequisites (manual, one-time)

- [x] Sign up for [Langfuse Cloud](https://cloud.langfuse.com) (free tier), create a project
- [x] Generate `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`, add to `.env` along with
      `LANGFUSE_HOST=https://cloud.langfuse.com`
- [x] Register per-token pricing in the Langfuse dashboard for each Groq model in use
      (`PLANNER_MODEL`, `REPLANNER_MODEL`, `PARAM_FIXER_MODEL`, `ANSWER_MODEL` — currently
      `openai/gpt-oss-20b` and `llama-3.1-8b-instant`) so `cost_details` populates
- [x] Add `langfuse` to `requirements.txt`, `pip install -r requirements.txt`
- [x] Run baseline (`python run_tests.py`) to confirm starting point before changes — 5/5 passed

---

## Step 1: Config + Shared Helper

- [x] `src/config.py`: add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`,
      `LANGFUSE_ENABLED` (derived: `bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)`)
- [x] New `src/utils/langfuse_helper.py`:
  - [x] `get_langfuse_client()` — singleton `Langfuse` client, or `None` if `LANGFUSE_ENABLED`
        is `False`
  - [x] `llm_generation(name, model, model_params, input_messages, run_id, session_id,
        extra_metadata=None)` context manager — `.output(...)` / `.usage(...)` methods, marks
        `level="ERROR"` on exception, no-op entirely when disabled

---

## Step 2: Graph-Level Trace (`src/core/pipeline.py`)

- [x] Attach Langfuse's LangGraph `CallbackHandler` to `graph.invoke()`'s `config["callbacks"]`
      when `LANGFUSE_ENABLED`
- [x] Set `trace_id = run_id`, `session_id = session_id` on the handler/trace
- [x] When disabled, `config` is unchanged from current behavior

---

## Step 3: Instrument Planner (`src/core/planner.py`)

- [x] Wrap `_call_groq`'s `client.chat.completions.create(...)` call in
      `llm_generation(name="planner", model=PLANNER_MODEL, ...)`
- [x] Feed `gen.output(raw)` and `gen.usage(...)` from `response.usage`
- [x] Pass `validation_retry` flag (already computed) into `extra_metadata`
- [x] Thread `session_id` into `_call_groq`/`plan()` signature (new param, defaults `None`)

---

## Step 4: Instrument Replanner (`src/core/replanner.py`)

- [x] Wrap its Groq call in `llm_generation(name="replanner", model=REPLANNER_MODEL, ...)`
- [x] Thread `session_id` into its signature (new param, defaults `None`)

---

## Step 5: Instrument Param Fixer (`src/core/param_fixer.py`)

- [x] Wrap `_call_groq`'s Groq call in `llm_generation(name="param_fixer",
      model=PARAM_FIXER_MODEL, ...)`
- [x] Thread `session_id` into its signature (new param, defaults `None`)

---

## Step 6: Instrument Answer Generator (`src/core/answer_generator.py`)

- [x] Wrap its Groq call in `llm_generation(name="answer_gen", model=ANSWER_MODEL, ...)`
- [x] Thread `session_id` into its signature (new param, defaults `None`)

---

## Step 7: Wire `session_id` Through Nodes (`src/core/nodes.py`)

- [x] `PipelineState` already carries enough context (`run_id`); confirm `session_id` is
      available where needed (via `config`/state) and passed to each of the 4 node functions'
      LLM calls from Steps 3-6

---

## Step 8: Verify

- [x] New `dev_checks/check_langfuse.py`:
  - [x] Run a simple query — confirm trace in Langfuse with `id=run_id`, `session_id` set,
        2 generations (`planner`, `answer_gen`), non-zero `usage_details`
  - [ ] Run a query expected to need a param fix — confirm additional `param_fixer`/
        `replanner` generations appear under the same trace (deferred — no reliable
        trigger query found; structurally covered since all 4 LLM calls share the
        same trace_context derivation)
- [x] `python run_tests.py` — confirm no regression (5/5 passed)
- [x] Confirm pipeline still works with `LANGFUSE_*` unset (no-op path) — temporarily unset
      and re-run `run_tests.py` (5/5 passed)

---

## Files Changed

| Action | File |
|---|---|
| **Updated** | `src/config.py`, `requirements.txt`, `.env`, `src/core/pipeline.py`, `src/core/planner.py`, `src/core/replanner.py`, `src/core/param_fixer.py`, `src/core/answer_generator.py`, `src/core/nodes.py` |
| **New** | `src/utils/langfuse_helper.py`, `dev_checks/check_langfuse.py` |
| **Unchanged** | `src/utils/logger.py`, `src/core/graph.py`, `app.py`, `eval/*`, all Pydantic response models |
