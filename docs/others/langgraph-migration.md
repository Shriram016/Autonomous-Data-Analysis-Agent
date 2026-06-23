# LangGraph Migration Guide — V1 → V2

## What's Changing

V1 uses raw Python orchestration (function calls, dicts, for-loops). V2 migrates to LangGraph where:
- Each pipeline component becomes a **node**
- Data flows through a **shared typed state** instead of function args and raw dicts
- Control flow (retry, replan, step progression) becomes **conditional edges** instead of nested loops
- **SQLite checkpointing** enables crash recovery / resumability

**The core logic inside each component stays the same.** Only the wiring and state plumbing changes.

---

## V1 Pipeline Flow (current)

```
User Query
    ↓
Schema Generator          → JSON schema (dtype + stats)
    ↓
Planner (LLM)             → Structured JSON plan (list of steps)
    ↓
Loop Controller
  ├── Executor._run_step  → Calls tool + critic per step
  │     ↓
  │   Tool Layer           → 9 predefined functions
  │     ↓
  │   Rule-Based Critic    → Deterministic checks
  │     ↓ pass / retry / replan
  └── (retry × 2, replan × 1, cap = len(plan) × 2)
    ↓
Answer Generator (LLM)    → Plain English answer
    ↓
Final Answer + Trace
```

---

## V2 LangGraph State

Single `TypedDict` shared across all nodes — replaces the scattered dicts and function args from V1.

```python
class PipelineState(TypedDict):
    # Inputs (set once at graph entry)
    query: str
    run_id: str
    original_df: pd.DataFrame

    # Schema Gen output
    schema: dict | None

    # Planner output
    plan: list[PlanStep]

    # Execution state
    state_store: dict[str, pd.DataFrame]   # tool outputs keyed by step name
    current_step_index: int
    retry_count: int
    total_executions: int
    max_executions: int
    trace: list[dict]

    # Final outputs
    final_df: pd.DataFrame | None
    status: str        # "success" | "error" | "unsolvable"
    message: str
    answer: str | None
```

---

## Node Mapping (V1 Component → V2 Node)

| V1 Component | V1 File | V2 Node | Changes |
|---|---|---|---|
| `generate_schema()` | `src/core/schema_gen.py` | `schema_gen_node` | Wrap as node; reads `original_df` from state, writes `schema` to state |
| `plan()` | `src/core/planner.py` | `planner_node` | Wrap as node; reads `query` + `schema` from state, writes `plan` to state |
| `_run_step()` | `src/core/executor.py` | `execute_step_node` | Runs ONE step per invocation (not the whole plan); reads/writes `state_store`, `trace`, `current_step_index` |
| `critique()` | `src/critics/rule_based_critic.py` | Stays inline inside `execute_step_node` | No change — it's 3 lines of delegation |
| `fix_params()` | `src/core/param_fixer.py` | `param_fixer_node` | **Currently a stub.** Becomes a real LLM node that takes failed step + error + schema → returns corrected PlanStep |
| `replan()` | `src/core/replanner.py` | `replanner_node` | **Currently a stub.** Becomes a real LLM node that generates a completely new plan |
| `generate_answer()` | `src/core/answer_generator.py` | `answer_gen_node` | Wrap as node; reads `query` + `final_df` from state, writes `answer` to state |

**Not a node:** Dataset loading happens before the graph runs. TOOL_REGISTRY, logging, and Streamlit UI are unchanged.

---

## Edge Design (replaces Loop Controller)

The nested for-loops in `src/core/loop_controller.py` become conditional edges:

```
schema_gen_node → planner_node → execute_step_node
                                       ↓
                                 (conditional edge)
                                 ├── success + more steps → execute_step_node  (loop back)
                                 ├── success + last step  → answer_gen_node
                                 ├── fail + retries left  → param_fixer_node → execute_step_node
                                 ├── fail + retries exhausted → replanner_node
                                 └── execution cap hit    → END (error)

replanner_node → (conditional edge)
               ├── success → execute_step_node  (restart with new plan)
               └── fail    → END (error)
```

---

## The One Blocker: Loop Controller Redesign

V1's Loop Controller has two nested loops:
- **Outer:** iterate through plan steps sequentially
- **Inner:** retry up to 2x per failed step, then fall back to replanner

LangGraph doesn't support nested for-loops. This must be **redesigned** as graph cycles with counters in state (`current_step_index`, `retry_count`). The conditional edge function reads these counters to decide the next node.

This is the only component that can't be wrapped as-is — it requires rethinking the control flow.

---

## Thing to Watch: DataFrames in State

LangGraph checkpointing serializes state. DataFrames aren't JSON-serializable. The SQLite checkpointer uses pickle, so it works — but `state_store` grows by one DataFrame per completed step, which makes checkpoints heavier. Acceptable for ~10K row dataset, but worth noting.

---

## New Components (not in V1)

| Component | Purpose |
|---|---|
| SQLite Checkpointer (`SqliteSaver`) | Wraps the graph for crash recovery — resume from last completed node |
| Real Param Fixer (LLM node) | Takes failed step + error message + critic check + query + schema → returns corrected PlanStep |
| Real Replanner (LLM node) | Takes original query + schema + failure context → returns a completely new plan |

---

## Build Order

1. Define `PipelineState` TypedDict
2. Port easy nodes: `schema_gen_node` → `planner_node` → `answer_gen_node`
3. Port `execute_step_node` (single step execution)
4. Wire the graph with conditional edges (replaces Loop Controller)
5. Implement real `param_fixer_node` (LLM)
6. Implement real `replanner_node` (LLM)
7. Add SQLite checkpointer
8. Update `app.py` to call the graph instead of `run_pipeline()`

---

## Files That Will Change

| File | What Happens |
|---|---|
| `src/core/pipeline.py` | **Replaced** — becomes the LangGraph graph definition |
| `src/core/loop_controller.py` | **Removed** — logic moves to conditional edges (in practice, kept in place but unused — its import in `pipeline.py` and related log branches are commented out, not deleted) |
| `src/core/executor.py` | **Refactored** — `_run_step` becomes a node; `execute()` function removed |
| `src/core/param_fixer.py` | **Rewritten** — stub becomes real LLM node |
| `src/core/replanner.py` | **Rewritten** — stub becomes real LLM node |
| `src/core/schema_gen.py` | **Unchanged** — core logic only |
| `src/core/planner.py` | **Unchanged** — core logic only |
| `src/core/answer_generator.py` | **Unchanged** — core logic only |
| `src/core/nodes.py` | **New** — centralized node adapter layer; wraps `schema_gen_node`, `planner_node`, `answer_gen_node` (Step 2), and later `execute_step_node`, `param_fixer_node`, `replanner_node` |
| `app.py` | **Updated** — calls graph instead of `run_pipeline()` |

**Unchanged:** `src/tools/*.py`, `src/critics/rule_based_critic.py`, `src/utils/`, `src/config.py`, `src/prompts/`
