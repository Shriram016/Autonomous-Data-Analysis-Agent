# Architecture — Autonomous Data Analysis Agent (ADAA)

## Pipeline Overview

```
User Query
    ↓
Schema Generator          → Dataset → concise JSON schema (never the raw df)
    ↓
Planner (LLM)             → Query + schema → JSON execution plan
    ↓
┌─────────────────────────────────────────────────────┐
│  LangGraph Execution Loop                           │
│  ┌───────────────────────────────────────────────┐  │
│  │ Executor                                      │  │
│  │     ↓                                         │  │
│  │ Tool Layer (10 predefined tools)              │  │
│  │     ↓                                         │  │
│  │ Rule-Based Critic (8 deterministic checks)    │  │
│  │     ↓                                         │  │
│  │ pass → next step     fail → Param Fixer (LLM) │  │
│  │                      fail → Replanner (LLM)   │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
    ↓
Answer Generator (LLM)   → DataFrame → plain English answer
    ↓
Final Answer + Reasoning Trace
```

The pipeline is orchestrated by **LangGraph** with structured state management. Each component is a graph node connected by conditional edges that handle step progression, retries, and replanning.

---

## Components

### Schema Generator
- **Input:** Raw DataFrame (9,994 rows × 21 columns)
- **Output:** Condensed JSON schema with per-column dtype, stats (min/max/median for numeric), sample values for categorical columns, date ranges for datetime
- **Why:** The LLM cannot receive the raw dataset — only the schema is passed to the Planner

```json
{
  "Order Date": {"dtype": "datetime64[ns]", "min": "2021-01-01", "max": "2024-12-31"},
  "Category":   {"dtype": "object", "unique_count": 3, "sample_values": ["Furniture", "Technology", "Office Supplies"]},
  "Sales":      {"dtype": "float64", "min": 0.44, "max": 22638.48, "median": 54.49}
}
```

---

### Planner (LLM)
- **Model:** `openai/gpt-oss-20b` via Groq API — temperature 0.0, reasoning model with `reasoning_effort: low`
- **Input:** User query + condensed schema + previous questions (if multi-turn session)
- **Output:** `{"status": "success", "plan": [...]}` or `{"status": "unsolvable", "reason": "..."}`
- **Validation:** Two layers — Pydantic models for structure + `_validate_plan()` for business logic (tool names, parameter signatures via `inspect`, sequential steps, state store chaining, mutual exclusion of `aggregate_column` and `groupby_aggregate`)
- **Retry:** Re-calls LLM once with the validation error injected if the plan fails checks

**Example plan — "Top 10 customers by sales in last 3 months":**
```json
[
  {"step": 1, "tool": "date_filter",       "parameters": {"col_name": "Order Date", "time_period": "3M", "end_date": "2024-12-31"}, "input": "original_df",    "output": "step_1_output"},
  {"step": 2, "tool": "groupby_aggregate", "parameters": {"group_col": "Customer Name", "agg_col": {"Sales": "sum"}},               "input": "step_1_output", "output": "step_2_output"},
  {"step": 3, "tool": "sort",              "parameters": {"sort_col": {"Sales_sum": "desc"}},                                        "input": "step_2_output", "output": "step_3_output"},
  {"step": 4, "tool": "top_n",             "parameters": {"N": 10},                                                                  "input": "step_3_output", "output": "step_4_output"}
]
```

---

### Tool Layer
10 predefined functions. The LLM selects tools and specifies parameters — it never generates free-form code.

| Tool | Purpose |
|---|---|
| `date_filter` | Filter rows within a lookback date range |
| `filter_by_condition` | Filter rows by a single column value (`==`, `!=`, `>`, `>=`, `<`, `<=`) |
| `extract_date_part` | Extract month / year / quarter / day into a new column |
| `column_arithmetic` | Arithmetic between two columns; supports datetime subtraction (result = days) |
| `groupby_aggregate` | Group by one or more columns and aggregate (sum, mean, count, min, max, median, std) |
| `aggregate_column` | Single aggregate over the whole dataset — no grouping; returns 1-row result |
| `sort` | Sort by one or more columns (ascending or descending) |
| `top_n` | Return the first N rows (always preceded by sort) |
| `select_columns` | Keep only specified columns, drop the rest |
| `rename_column` | Rename columns via a mapping |

---

### Executor + State Store
- Reads each step from the plan, calls the correct tool, and manages intermediate outputs in a state store
- **State store:** `{"original_df": df, "step_1_output": df, ...}` — each step reads from the previous step's output
- A failed step is never skipped — downstream steps depend on its output
- Partial trace returned on failure — all records up to the failure point are included

---

### Rule-Based Critic
Runs after every tool call. Deterministic, no LLM — fast and cheap. First failing check short-circuits the rest.

| Check | What It Catches |
|---|---|
| Result is not None | Silent tool crash |
| Result is not empty | Over-filtering removed all rows |
| No fully empty columns | Key columns have no data |
| Expected columns present | Wrong or dropped column names |
| groupby row count = unique group values | Aggregation correctness |
| top_n rows ≤ N | top_n working correctly |
| Date filter within specified range | date_filter correctness |
| Aggregated columns are numeric | Type integrity after groupby |

---

### Param Fixer (LLM)
- **Model:** `openai/gpt-oss-20b` via Groq API — temperature 0.0
- **Triggered:** When a step fails critic checks and retries are available (max 2 retries per step)
- **Input:** Failed step, error message, critic check name, original query, schema
- **Output:** Corrected parameters for the failed step
- The executor re-runs the step with the corrected parameters

---

### Replanner (LLM)
- **Model:** `openai/gpt-oss-20b` via Groq API — temperature 0.0
- **Triggered:** When all retries for a step are exhausted (max 1 replan attempt)
- **Input:** Original query, schema, failed plan, error history
- **Output:** A completely new execution plan starting from `original_df`
- Execution restarts from step 1 of the new plan

---

### LangGraph Execution Loop
Replaces the V1 manual loop controller. Retry and replan logic is implemented as conditional edges in the graph.

```
schema_gen → planner → execute_step
                            |
              (conditional edge after execute_step)
              ├── success + more steps     → execute_step (loop back)
              ├── success + last step      → answer_gen
              ├── fail + retries left      → param_fixer → execute_step
              ├── fail + retries exhausted → replanner
              └── execution cap hit        → END (error)

replanner → (conditional edge)
              ├── success → execute_step (restart with new plan)
              └── fail    → END (error)
```

**Limits:**
- Per-step retry limit: 2 (3 total attempts per step)
- Max replan attempts: 1
- Total execution cap: `len(plan) × 2`

---

### Answer Generator (LLM)
- **Model:** `llama-3.1-8b-instant` via Groq API — temperature 0.3
- **Input:** User query + final computed DataFrame
- **Output:** Plain English summary of the result (2-3 sentences)
- Runs once after the execution loop completes — outside the retry loop
- Failure is non-critical: pipeline returns the DataFrame regardless

**Known limitation:** The answer generator can hallucinate arithmetic when summarizing multi-row DataFrames. It should not be relied upon to sum, re-aggregate, or derive values from the data — it is only reliable when restating values already present in the result.

---

### Session Memory
- Stores the last 3 user questions per session in the LangGraph state (`recent_questions` field)
- Previous questions are passed to the Planner so follow-up queries like "What about 2015?" can resolve context from prior turns
- Session state persists across turns via LangGraph's SQLite checkpointer keyed by `session_id`
- Each query still runs on `original_df` from scratch — no result reuse across turns

---

### Observability

**File logging:**
- One log file per run: `logs/run_YYYY_MM_DD_HH_MM_SS.log`
- Unique `run_id` links every event for a query
- Console handler (INFO) + file handler (DEBUG)

**Langfuse tracing:**
- Every LLM call (Planner, Param Fixer, Replanner, Answer Generator) is instrumented as a Langfuse generation
- Captures: prompt, response, model name, token usage, latency
- Traces are linked by `run_id` and grouped by `session_id`

---

### Streamlit UI
Conversation-style chat interface using Streamlit's native chat elements (`st.chat_message`, `st.chat_input`).

- Chat history displayed oldest → newest in a scrollable container
- Each turn shows the user's question and the assistant's plain English answer
- Detailed view (result table, execution trace, plan steps) rendered for the latest turn only
- Sidebar: session info (session ID, recent questions) and "New Session" button

---

## Pipeline State

All components share a single typed state object (`PipelineState`) passed through the LangGraph graph:

```python
class PipelineState(TypedDict):
    # Inputs
    query: str
    run_id: str
    session_id: str
    original_df: pd.DataFrame
    recent_questions: list[str]

    # Schema Gen output
    schema: Optional[dict]

    # Planner output
    plan: list[PlanStep]
    max_executions: int

    # Execution state
    state_store: dict[str, pd.DataFrame]
    current_step_index: int
    retry_count: int
    total_executions: int
    trace: list[dict]

    # Final outputs
    final_df: Optional[pd.DataFrame]
    status: str
    message: str
    answer: Optional[str]
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Free code gen vs predefined tools | Predefined tools | Safe, validatable, debuggable — no black box |
| Critic type | Rule-based only (deterministic) | LLM critic adds latency without reliable signal |
| State store | Dict keyed by step output name | Enables retry from the failure point, not from scratch |
| Retry limits | 2 retries + 1 replan + dynamic cap | Prevents infinite loops while allowing self-correction |
| Schema passed to Planner | Condensed (dtype + min/max + sample values) | Fewer tokens; model handles narrow structured tasks better |
| groupby + aggregate | Single combined tool | `groupby` alone returns an unusable GroupBy object, never a DataFrame |
| Answer Generator failure | Non-critical — pipeline returns DataFrame regardless | Narration is supplementary; computed data is the primary output |
| Session memory scope | Questions only — not answers or DataFrames | Each query runs on original_df from scratch; no result reuse |
| Orchestration framework | LangGraph | Conditional edges replace manual loop logic; structured state replaces raw dicts |
