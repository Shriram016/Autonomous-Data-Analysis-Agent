# CLAUDE.md — Autonomous Data Analysis Agent (ADAA)

## What This Project Is

A deterministic, traceable AI pipeline that takes a dataset and a natural language question and returns a **verified, computed answer with full reasoning trace** — not a chatbot response. Every step is logged, validated, and recoverable.

**Core constraint:** The system never generates free-form pandas code. It uses a predefined tool layer only. This makes every execution safe, predictable, and debuggable.

---

## Dataset

**Sample Superstore** (~9,994 rows, 21 columns)
Key columns: `Order Date`, `Ship Date`, `Category`, `Sub-Category`, `Sales`, `Quantity`, `Discount`, `Profit`, `Customer Name`, `State`, `Region`, `Segment`

---

## Pipeline Architecture

```
User Query
    ↓
Schema Generator          → JSON schema (dtype + stats), never the raw df
    ↓
Planner (LLM)             → Structured JSON plan (list of steps with tool + params)
    ↓
Loop Controller
  ├── Executor            → Reads plan steps, calls tools, manages state store
  │     ↓
  │   Tool Layer          → 9 predefined functions (no free code gen)
  │     ↓
  │   Rule-Based Critic   → Deterministic checks after every step
  │     ↓ pass/retry/replan
  └── (retry up to 2x per step, 1 replan, max steps = plan length × 2)
    ↓
Answer Generator (LLM)   → Plain English description of the result DataFrame
    ↓
Final Answer + Trace + Natural Language Description
```

---

## Build Status

| Component | File | Status |
|---|---|---|
| Tool Layer (9 tools) | `src/tools/*.py` | ✅ Done |
| TOOL_REGISTRY | `src/tools/tools.py` | ✅ Done |
| Shared helpers | `src/utils/helpers.py` | ✅ Done |
| Schema Generator | `src/core/schema_gen.py` | ✅ Done |
| Config | `src/config.py` | ✅ Done |
| Environment | `.env`, `.gitignore` | ✅ Done |
| Dependencies | `requirements.txt` | ✅ Done |
| Planner system prompt | `src/prompts/planner_prompt.py` | ✅ Done |
| Planner (LLM) | `src/core/planner.py` | ✅ Done |
| Executor + State Store | `src/core/executor.py` | ✅ Done |
| Rule-Based Critic | `src/critics/rule_based_critic.py` | ✅ Done |
| Loop Controller | `src/core/loop_controller.py` | ✅ Done |
| Pipeline | `src/core/pipeline.py` | ✅ Done |
| Answer Generator | `src/core/answer_generator.py` | ✅ Done |
| Observability/Logging | `src/utils/logger.py` | ✅ Done |
| End-to-End Tests | `run_tests.py` | ✅ 5/5 passing |
| Param Fixer | `src/core/param_fixer.py` | ⏳ Stub only |
| Replanner | `src/core/replanner.py` | ⏳ Stub only |
| Streamlit UI | `app.py` | ✅ Done |
| Evaluation Pipeline | `eval/` | ⏳ Not built |

---

## Components

### 1. Schema Generator ✅
- Input: raw dataframe
- Output: JSON with per-column dtype, stats (min/max/median for numeric), up to 10 unique values for categorical, min/max dates for datetime
- Also captures: null count, null percentage, missingness flag (none/low/moderate/high)
- Why: LLM cannot receive 9,994 rows — only the schema is passed to the Planner
- Failure: returns error if df is empty or unreadable

### 2. Planner (LLM) ✅
- Input: user query + schema JSON (condensed — dtype + min/max + sample values only)
- Output: `{"status": "success", "plan": [...]}` or `{"status": "unsolvable", "reason": "..."}` or `{"status": "error", "message": "..."}`
- Model: `llama-3.1-8b-instant` via Groq API, temperature=0.0, max_tokens=1024
- Structured output: Pydantic models (`PlanStep`, `PlanResponse`) for structure validation
- Business logic validation: `_validate_plan()` checks tool names, parameter names + presence (via `inspect`), sequential steps, state store chaining
- Retry: once on any failure (API error or Pydantic validation error)
- Key constraint: outputs machine-readable JSON only, never free-form text
- Quarter filtering: uses `extract_date_part` (part="quarter") → `filter_by_condition` — NOT `date_filter`
- Ambiguous dates: uses schema max date as `end_date`

### 3. Tool Layer (9 tools) ✅
All tools return: `{"status": "success|error", "message": "...", "result": <df or None>}`

| Tool | Parameters | Purpose |
|---|---|---|
| `date_filter` | df, col_name, time_period, end_date | Filter rows within date range (lookback from end_date) |
| `filter_by_condition` | df, col_name, col_type, val_to_filter, operator | Filter rows by column value |
| `extract_date_part` | df, col_name, part, new_col_name | Extract month/year/quarter/day into new column |
| `column_arithmetic` | df, col1, col2, operation, new_col_name, is_datetime | Arithmetic between two columns |
| `groupby_aggregate` | df, group_col, agg_col (dict) | GroupBy + aggregate (merged — groupby alone returns unusable object) |
| `sort` | df, sort_col (dict) | Sort by one or more columns (asc/desc) |
| `top_n` | df, N | Return top N rows (always apply sort before top_n) |
| `select_columns` | df, col_list | Keep only specified columns |
| `rename_column` | df, rename_map (dict) | Rename columns via mapping |

### 4. Executor ✅
- Input: full planner output dict + original dataframe
- Output: `{"status", "final_df", "message", "trace"}`
- State store: `{"original_df": df, "step_1_output": df, "step_2_output": df, ...}` — internal only, not returned
- Components: `_init_state_store`, `_call_tool`, `_critic`, `_build_trace_record`, `_run_step`, `execute`
- Each step fetches input from state store, calls tool, passes result to critic, builds trace record
- `_critic` delegates to Rule-Based Critic — accepts `input_df` alongside `result_df`
- Trace captures per-step: tool, parameters, status, message, output shape, column names, critic verdict
- Hard stops on: missing state store key, tool not in registry, tool crash, None result, critic fail
- Partial trace returned on failure — all records up to point of failure included

### 5. Rule-Based Critic ✅
- Runs after every tool call — deterministic, no LLM
- Checks (8 total): df not None, df not empty, no fully-empty columns, expected columns exist (per-tool derivation), groupby row count = unique groups, top_n rows ≤ N, date filter within range (all dates ≤ end_date), numeric agg columns are numeric (groupby_aggregate only)
- Output: `{"status": "pass"}` or `{"status": "fail", "check": str, "reason": str}`
- First failing check short-circuits — rest are skipped

### 6. Loop Controller ✅
- Entry point: `run(planner_output, df, query, schema)`
- Per-step retry limit: 2 (1 original + 2 retries = 3 total attempts per step)
- Max executions cap: `len(plan) * 2` — dynamic, not hardcoded
- Retry flow: step fails → `fix_params` (stub) → retry → retry → replan (stub) → return partial result + explanation
- Never skips a failed step (downstream steps depend on its output)
- Returns `total_executions` count alongside trace for observability

### 7. Param Fixer ⏳ (stub only)
- Called between retries when a step fails
- Will use LLM to diagnose error and return corrected parameters for the failed step only
- Receives: failed step + error message + critic check name + query + schema
- Currently returns the step unchanged
- File: `src/core/param_fixer.py`

### 8. Replanner ⏳ (stub only)
- Called after all retries for a step are exhausted
- Generates a completely new plan from scratch using original_df
- Receives: original planner output + error context (failed step, message, trace so far) + query + schema
- Currently returns error (not yet implemented)
- File: `src/core/replanner.py`

### 9. Pipeline ✅
- Single entry point: `run_pipeline(query)` wires all 5 stages in order
- Returns: `{run_id, status, query, schema, plan, final_df, answer, message, trace, total_executions}`
- Graceful degradation: answer_generator failure does not fail the pipeline
- Top-level try/except captures unexpected crashes to log file

### 10. Answer Generator ✅
- Input: user query + final DataFrame (post-aggregation, always small)
- Output: `{"status": "success", "answer": str}` or `{"status": "error", "message": str}`
- Model: `llama-3.1-8b-instant` via Groq API, temperature=0.3, max_tokens=256, 90s timeout
- No retry — narration failure is non-critical, pipeline returns DataFrame regardless
- LLM narrates computed data only — no hallucination risk on numbers
- System prompt enforces: direct answer, exact numbers, plain English, no technical jargon

### 11. Observability / Logging ✅
- `get_logger(run_id)` — console handler (INFO) + file handler (DEBUG)
- Log files: `logs/run_YYYY_MM_DD_HH_MM_SS.log` — one per pipeline run
- `LOG_LLM_PROMPTS: bool = False` — toggle to expand full system/user prompt in log file
- Logged events: query_received, data_loader, schema_gen, planner, loop_controller, tool_call_started/completed (with params + shape), step_executed, final_result (with row preview), answer_gen, pipeline_complete/error
- Console: compact one-liner per event; File: timestamped, expanded detail for key events

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python |
| Data operations | Pandas |
| LLM | Groq API — `llama-3.1-8b-instant` |
| Data validation | Pydantic |
| UI | Streamlit |
| Logging | Python logging / plain text .log files |

---

## Key Architectural Decisions

| Decision | Choice | Reason |
|---|---|---|
| Free code gen vs predefined tools | Predefined tools | Safe, validatable, debuggable — no black box |
| Tool count | 9 tools (expanded from 6) | Added extract_date_part, column_arithmetic, select_columns, rename_column for full query coverage |
| groupby + aggregate | Single combined tool | groupby alone returns unusable GroupBy object |
| Critic placement | Rule-based inside loop only | LLM critic removed — rule-based checks cover all structural failures; semantic validation adds latency without reliable signal |
| State store | Dict keyed by step output name | Enables retry from failure point, not from scratch |
| Retry limits | 2 retries + 1 replan + dynamic cap (len(plan) × 2) | Prevents infinite loops while allowing self-correction — cap scales with plan size |
| Schema passed to Planner | Condensed (dtype + min/max + sample values) | Fewer tokens, 8B model handles it better |
| Planner output format | `{"status": ..., "plan": [...]}` wrapper | Consistent parsing — no type-checking needed |
| Structured output | Pydantic (`PlanStep`, `PlanResponse`) | Catches structure/type mismatches before executor runs |
| Plan validation | Two layers: Pydantic + `_validate_plan()` | Pydantic = structure, `_validate_plan()` = business logic |
| Quarter filtering | `extract_date_part` → `filter_by_condition` | `date_filter` uses lookback — not suited for fixed calendar quarters |
| Ambiguous dates | Use schema max date as `end_date` | Safe default, no hallucination |
| Unsolvable queries | Return `{"status": "unsolvable", "reason": "..."}` | No partial plan, no hallucinated tools |
| LLM model | `llama-3.1-8b-instant` | Planner task is narrow/structured — 8B is sufficient, faster |
| Validation | Rule-based critic only (intermediate, per-step) | LLM critic removed — deterministic checks are sufficient and keep the pipeline fully traceable |
| `_call_groq` return type | Always `Dict` — wraps `PlanResponse` in `{"status": "success", "data": parsed}` | Consistent return type, no isinstance checks needed in caller |
| Parameter validation in `_validate_plan` | Uses `inspect.signature()` against real tool fn | Catches missing/unknown params before Executor runs — no runtime surprises |
| State store | Internal to Executor, not returned in output | Trace (shape + columns) is sufficient for debuggability — raw dfs are heavy |
| Critic signature | `_critic(step, tool_response, result_df, input_df)` | `input_df` added to support groupby row count and expected columns checks |
| Retry logic | Not in Executor or Tool Caller — Loop Controller only | Single responsibility — Executor executes, Loop Controller decides retry/replan |

---

## Planner Output Format

```python
# Success
{"status": "success", "plan": [PlanStep, ...]}

# Unsolvable
{"status": "unsolvable", "reason": "..."}

# Error (API failure, parse error, validation failure)
{"status": "error", "message": "..."}
```

Each `PlanStep`:
```json
{
  "step": 1,
  "tool": "date_filter",
  "parameters": {"col_name": "Order Date", "time_period": "3M", "end_date": "2024-12-31"},
  "input": "original_df",
  "output": "step_1_output"
}
```

---

## Target Queries (5 Test Cases)

| # | Query | Reasoning Type |
|---|---|---|
| 1 | Count of orders per month, sorted highest to lowest | Grouping + sorting |
| 2 | Sales of Furniture in California in Q1 | Multi-condition filtering |
| 3 | How long does shipping take? Are certain products faster? | Derived column calculation |
| 4 | Is there a month-wise sales trend per product category? | Trend analysis |
| 5 | Top 10 customers by sales in last 3 months | Date filter + groupby + rank |

---

## Failure Modes (Demonstrate These)

| Failure | Trigger | Expected Behaviour |
|---|---|---|
| Wrong column name in plan | Ambiguous query | Rule critic catches, LLM corrects params, retry |
| Empty result after filter | Over-specific filter | Rule critic catches empty df, retry with relaxed filter |
| Ambiguous time reference | "recent sales" with no date | Planner uses dataset max date |
| Max retries exceeded | Repeatedly wrong params | Loop controller stops, returns partial result + explanation |
| Wrong sort order | "worst performing" → descending | Known limitation — no longer caught since LLM critic removed; Planner quality is the guard here |

---

## Evaluation Pipeline

- Test set: 20–30 queries with manually computed ground truth
- Metrics: query success rate, step accuracy, tool correctness, error recovery rate, trace completeness
- Validation is at two levels: intermediate step outputs AND final answer — correct answer via wrong reasoning is still a system failure

---

## Streamlit UI Panels

1. Query input box
2. Answer panel — LLM-generated plain English answer (shown first)
3. Result table — final DataFrame output
4. Execution trace panel — per-step tool, status, critic verdict, output shape
5. Plan panel — steps planned by the LLM
6. Schema panel — condensed schema sent to Planner

---

## Build Phases

- **Week 1:** Schema generator, Planner, Tool layer (all 9), Executor with state store, basic end-to-end run
- **Week 2:** Rule-based critic, Loop controller, Param fixer, Replanner, Observability/logging, full error handling
- **Week 3:** Evaluation pipeline + test set, Streamlit UI, README + architecture diagram, demo with failure cases
