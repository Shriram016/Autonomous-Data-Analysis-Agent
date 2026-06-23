# Langfuse Observability — Design (V2 §3)

## What's Changing

Today, observability is plain-text logging only ([src/utils/logger.py](../src/utils/logger.py)) —
every pipeline run writes structured events to a `.log` file: prompts sent, raw LLM responses,
plan steps, validation failures, etc. This is good for debugging a single run, but there's no
UI, no token/cost tracking, and no way to browse "how many queries needed the param fixer this
week" without grepping log files.

V2 §3 adds [Langfuse](https://langfuse.com) (Cloud, free tier) as an **additional**, queryable
view on top — it doesn't replace `.log` files. For every `run_pipeline()` call, Langfuse gets:

- **One trace per query** (`trace.id = run_id`, `trace.session_id = session_id`)
- **One span per LangGraph node** (`schema_gen`, `planner`, `execute_step`, `param_fixer`,
  `replanner`, `answer_gen`) — automatic, via LangGraph's built-in Langfuse `CallbackHandler`
- **One "generation" observation per LLM call** — `planner`, `replanner`, `param_fixer`,
  `answer_gen` — each capturing prompt, response, model, model parameters, token usage, and
  (once pricing is registered) cost

**Scope boundary:** read-only observability. No change to pipeline logic, control flow,
retry/replan behavior, or output schemas (`PlanResponse`, `ParamFixResponse`, etc.). If Langfuse
isn't configured (no API keys), the pipeline behaves **exactly as it does today** — every
Langfuse call is a no-op.

---

## Setup (one-time, manual — not code)

1. Sign up for [Langfuse Cloud](https://cloud.langfuse.com) (free tier)
2. Create a project, generate `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`
3. Add to `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com
   ```
4. In the Langfuse dashboard, register per-token pricing for each Groq model in use
   (`openai/gpt-oss-20b`, `llama-3.1-8b-instant`, and whichever models `PLANNER_MODEL` /
   `REPLANNER_MODEL` / `PARAM_FIXER_MODEL` / `ANSWER_MODEL` resolve to) — Groq models aren't in
   Langfuse's built-in pricing table, so `cost_details` will show $0 until this is done.
5. Add `langfuse` to `requirements.txt`

---

## Architecture

```
run_pipeline(query, session_id)
        │
        ├─ Langfuse CallbackHandler attached to graph.invoke() config
        │     trace.id = run_id, trace.session_id = session_id
        │     -> automatic span per LangGraph node:
        │        schema_gen, planner, execute_step, param_fixer, replanner, answer_gen
        │
        └─ Inside planner_node / replanner_node / param_fixer_node / answer_gen_node:
              _call_groq() (or equivalent) wrapped in llm_generation(...) context manager
              -> nested "generation" observation under the current node's span:
                 name="planner"/"replanner"/"param_fixer"/"answer_gen"
                 input, output, model, model_parameters, usage_details, metadata, level
```

If `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are unset: `get_langfuse_client()` returns `None`,
`CallbackHandler` is not attached, and `llm_generation()` is a no-op context manager — zero
behavior change, matches the existing `if logger and run_id:` pattern used for `.log` logging.

---

## Config Additions (`src/config.py`)

```python
LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
LANGFUSE_ENABLED: bool = bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)
```

---

## Shared Helper — `src/utils/langfuse_helper.py` (new)

Two pieces, both no-op safe when `LANGFUSE_ENABLED` is `False`:

1. **`get_langfuse_client()`** — returns a singleton `Langfuse` client configured from
   `LANGFUSE_*` config vars, or `None` if disabled.

2. **`llm_generation(name, model, model_params, input_messages, run_id, session_id, extra_metadata=None)`**
   — a context manager wrapping one Groq API call:
   - On enter: starts a Langfuse "generation" observation (`name`, `model`, `model_parameters`,
     `input`, `metadata={"run_id": run_id, "session_id": session_id, **extra_metadata}`)
   - On the caller setting `.output(raw_response_text)` and `.usage(prompt_tokens,
     completion_tokens, total_tokens)` (from `response.usage`) before exit
   - On exception: marks `level="ERROR"`, `status_message=str(exception)`
   - If `LANGFUSE_ENABLED` is `False`: every method is a no-op, `__enter__`/`__exit__` do nothing

This is the "wrapper around the existing function" — each of the 4 LLM-calling functions adds a
`with llm_generation(...) as gen:` block around its existing `client.chat.completions.create(...)`
call, with one or two lines to feed `gen.output(...)` / `gen.usage(...)` from the response
already being read. No control-flow, retry, or validation logic changes.

---

## Graph-Level Trace — `src/core/pipeline.py`

Where `graph.invoke(initial_state, config=config)` is called: attach Langfuse's LangGraph
`CallbackHandler` to `config["callbacks"]`, with `trace_id=run_id` and `session_id=session_id`.
If `LANGFUSE_ENABLED` is `False`, skip this entirely — `config` is unchanged from today.

This is the only pipeline.py change. It gives the per-node spans automatically — LangGraph emits
callback events for every node's start/end regardless of what's inside the node.

---

## Per-LLM-Call Generations (4 files)

| File | Function | `name` |
|---|---|---|
| `src/core/planner.py` | `_call_groq` | `"planner"` |
| `src/core/replanner.py` | (its Groq call) | `"replanner"` |
| `src/core/param_fixer.py` | `_call_groq` | `"param_fixer"` |
| `src/core/answer_generator.py` | (its Groq call) | `"answer_gen"` |

Each wraps its existing `client.chat.completions.create(...)` call:

```python
with llm_generation(
    name="planner",
    model=PLANNER_MODEL,
    model_params={"temperature": PLANNER_TEMPERATURE, "max_tokens": PLANNER_MAX_TOKENS, "reasoning_effort": "low"},
    input_messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": effective_prompt}],
    run_id=run_id,
    session_id=session_id,
    extra_metadata={"validation_retry": error_context is not None},
) as gen:
    response = client.chat.completions.create(...)
    raw = response.choices[0].message.content
    gen.output(raw)
    gen.usage(response.usage.prompt_tokens, response.usage.completion_tokens, response.usage.total_tokens)
```

**Note:** `replanner.py` and `answer_generator.py` currently don't receive `session_id` as a
parameter — they'll need it threaded through from `pipeline.py`/`nodes.py` (small signature
addition, same pattern as `run_id` is already threaded for logging).

---

## Verification — `dev_checks/check_langfuse.py` (new)

1. Run one simple query (resolves in `planner` → `answer_gen`, 2 generations)
2. Run one query expected to need a param fix (more generations: `planner` → `param_fixer` →
   ... → `answer_gen`)
3. For each: confirm the trace appears in the Langfuse dashboard (or via Langfuse's API) with
   the correct `id` (= `run_id`), `session_id`, expected generation `name`s/count, and non-zero
   `usage_details`
4. Confirm `python run_tests.py` still passes unchanged (no regression to pipeline output)

---

## Files That Will Change

| File | Change |
|---|---|
| `src/config.py` | Add `LANGFUSE_*` config vars |
| `requirements.txt` | Add `langfuse` |
| `src/utils/langfuse_helper.py` | **New** — `get_langfuse_client()`, `llm_generation()` context manager |
| `src/core/pipeline.py` | Attach Langfuse `CallbackHandler` to `graph.invoke()` config (trace_id=run_id, session_id=session_id) |
| `src/core/planner.py` | Wrap `_call_groq`'s Groq call in `llm_generation(name="planner", ...)` |
| `src/core/replanner.py` | Wrap its Groq call in `llm_generation(name="replanner", ...)`; thread `session_id` through |
| `src/core/param_fixer.py` | Wrap `_call_groq`'s Groq call in `llm_generation(name="param_fixer", ...)`; thread `session_id` through |
| `src/core/answer_generator.py` | Wrap its Groq call in `llm_generation(name="answer_gen", ...)`; thread `session_id` through |
| `dev_checks/check_langfuse.py` | **New** — verification script |
| `.env` | Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` |

**Unchanged:** `src/utils/logger.py` (kept as-is, additive), `src/core/graph.py` node wiring,
`PlanResponse`/`ParamFixResponse`/output schemas, retry/replan/critic logic, `app.py`,
`eval/*`.
