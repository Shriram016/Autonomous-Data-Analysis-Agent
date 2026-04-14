# Autonomous Data Analysis Agent (ADAA)

## Project Overview

A system where a user gives a dataset and a natural language question, and the agent returns a correct computed answer, explanation, and full reasoning trace — not just a response, but a verifiable, traceable result.

This is not a chatbot. It is a **pipeline with checkpoints.** Every component has a clear input, a clear output, and a defined failure condition.

---

## Why This Project

- **Verifiable output** — the answer is either correct or not. No hiding behind vague text
- **Reasoning trace** — full transparency into agent decisions, not a black box
- **Deterministic safety** — no free-form code generation; only predefined tools are called
- **Business relevance** — solves a real analytical problem any company faces

---

## Dataset

**Sample Superstore Dataset**
- Source: https://www.kaggle.com/datasets/vivek468/superstore-dataset-final
- Rows: ~9,994
- Columns: 21

```
Row ID, Order ID, Order Date, Ship Date, Ship Mode,
Customer ID, Customer Name, Segment, Country, City, State,
Postal Code, Region, Product ID, Category, Sub-Category,
Product Name, Sales, Quantity, Discount, Profit
```

---

## Target Queries (Test Coverage)

These 5 queries cover different reasoning types and stress test different parts of the pipeline:

| # | Query | Reasoning Type |
|---|---|---|
| 1 | Count of orders for each month sorted highest to lowest | Grouping + sorting |
| 2 | Sales of Furniture in California in Q1? | Multi-condition filtering |
| 3 | How much time taken to ship a product once order is placed? Are certain products shipped faster? | Derived column calculation |
| 4 | Is there a trend/pattern with sales month-wise for certain product categories? | Trend analysis |
| 5 | Top 10 customers that contributed to max sales in last 3 months | Date filter + groupby + rank |

---

## System Architecture

```
User Query
    ↓
Schema Generator
    ↓
Planner (LLM)
    ↓
┌─────────────────────────────────────────┐
│  Loop Controller                        │
│  ┌─────────────────────────────────┐    │
│  │ Executor                        │    │
│  │     ↓                           │    │
│  │ Tool Layer                      │    │
│  │     ↓                           │    │
│  │ Rule-Based Critic               │    │
│  │     ↓ (pass / retry / replan)   │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
    ↓
Answer Generator (LLM narrates result)
    ↓
Final Answer + Trace
```

---

## Component Design

### 1. Schema Generator

**Purpose:** Converts the raw dataset into a concise JSON description that the Planner can reason over. The full dataset (9,994 rows) cannot be passed to an LLM — only the schema is passed.

**Input:** Raw dataframe

**Output:** Condensed schema JSON (dtype + min/max + sample values only)

**Logic:**
- For every column: capture column name and dtype
- For numeric columns (int/float): capture min, max, median
- For categorical columns: capture unique count; sample values only for low-cardinality columns (≤15 unique values)
- For datetime columns: capture min date and max date
- Identifier/non-analytical columns excluded (Row ID, Order ID, Customer ID, etc.)

**Example Output:**
```json
{
  "Order Date": {"dtype": "datetime64[ns]", "min": "2021-01-01", "max": "2024-12-31"},
  "Category": {"dtype": "object", "unique_count": 3, "sample_values": ["Furniture", "Technology", "Office Supplies"]},
  "Sales": {"dtype": "float64", "min": 0.44, "max": 22638.48, "median": 54.49}
}
```

**Failure:** Returns `{"status": "error", "message": "..."}` if dataframe is empty or unreadable.

---

### 2. Planner (LLM)

**Purpose:** Converts a natural language query into a structured, executable step-by-step plan.

**Input:**
- User query (natural language)
- Condensed schema JSON (from schema generator)

**Output:** Validated JSON plan with explicit steps, or an unsolvable/error response.

**Model:** `llama-3.1-8b-instant` via Groq API — temperature=0.0, max_tokens=1024

**Validation — two layers:**
1. Pydantic (`PlanStep`, `PlanResponse`) — validates structure and types
2. `_validate_plan()` — checks tool names, parameter names/presence (via `inspect.signature()`), sequential step numbers, unbroken state store chain

**Output format:**
```json
{"status": "success", "plan": [...]}
{"status": "unsolvable", "reason": "..."}
{"status": "error", "message": "..."}
```

**Example Plan for "Top 10 customers by sales in last 3 months":**
```json
{
  "status": "success",
  "plan": [
    {
      "step": 1,
      "tool": "date_filter",
      "parameters": {"col_name": "Order Date", "time_period": "3M", "end_date": "2024-12-31"},
      "input": "original_df",
      "output": "step_1_output"
    },
    {
      "step": 2,
      "tool": "groupby_aggregate",
      "parameters": {"group_col": "Customer Name", "agg_col": {"Sales": "sum"}},
      "input": "step_1_output",
      "output": "step_2_output"
    },
    {
      "step": 3,
      "tool": "sort",
      "parameters": {"sort_col": {"Sales_sum": "desc"}},
      "input": "step_2_output",
      "output": "step_3_output"
    },
    {
      "step": 4,
      "tool": "top_n",
      "parameters": {"N": 10},
      "input": "step_3_output",
      "output": "step_4_output"
    }
  ]
}
```

**Retry:** Once on any failure (API error or validation error).

---

### 3. Tool Layer

**Purpose:** A set of 9 predefined, callable functions. The LLM never writes free pandas code — it only selects tools and specifies parameters.

**Why predefined tools over free code generation:**
- Free code generation produces a black box every time — unpredictable, unsafe, hard to validate
- Predefined tools have known input/output schemas — making validation, debugging, and observability straightforward
- Every tool failure is caught the same way — no surprises

**Standard Response Format (all tools):**
```json
{"status": "success|error", "message": "...", "result": <dataframe or None>}
```

**Tool Definitions:**

| Tool | Parameters | Purpose |
|---|---|---|
| `date_filter` | df, col_name, time_period, end_date | Filter rows within a lookback date range ending at end_date |
| `filter_by_condition` | df, col_name, col_type, val_to_filter, operator | Filter rows by a single column value |
| `extract_date_part` | df, col_name, part, new_col_name | Extract month/year/quarter/day into a new column |
| `column_arithmetic` | df, col1, col2, operation, new_col_name, is_datetime | Arithmetic between two columns; use is_datetime=true for date subtraction |
| `groupby_aggregate` | df, group_col, agg_col (dict) | GroupBy one or more columns + aggregate |
| `sort` | df, sort_col (dict) | Sort by one or more columns asc/desc |
| `top_n` | df, N | Return top N rows (always sort before top_n) |
| `select_columns` | df, col_list | Keep only specified columns, drop the rest |
| `rename_column` | df, rename_map (dict) | Rename columns via a mapping |

**Key Design Decision:** `groupby` and `aggregate` are merged into a single tool (`groupby_aggregate`) because groupby alone returns a GroupBy object, not a usable dataframe. They are always used together.

---

### 4. Executor

**Purpose:** Reads each step from the planner's JSON plan, calls the correct tool with the correct parameters, and manages the flow of intermediate outputs between steps.

**Input:** Validated plan from Planner + original DataFrame

**Output:** `{"status", "final_df", "message", "trace"}`

**State Store:**
```python
state = {
  "original_df": <full dataset>,
  "step_1_output": <df after step 1>,
  "step_2_output": <df after step 2>,
  ...
}
```

The state store is internal to the Executor — it is not returned in the pipeline output. The trace (shape + columns per step) is sufficient for debuggability without carrying full DataFrames.

**Flow per step:**
1. Fetch input df from state store by key
2. Call the specified tool with parameters
3. Pass result to Rule-Based Critic
4. If critic passes → store output in state store → move to next step
5. If critic fails → return error + partial trace to Loop Controller

---

### 5. Rule-Based Critic

**Purpose:** Validates tool outputs after every step. Catches silent failures — cases where the tool ran without error but produced wrong or unusable output.

**When it runs:** After every single tool execution, inside the loop.

**Type:** Deterministic — no LLM, fast and cheap. First failing check short-circuits the rest.

**Checks performed:**

| Check | What It Catches |
|---|---|
| df is not None | Tool crashed silently |
| df is not empty | Tool filtered out all rows |
| No fully empty columns | Key columns have no data |
| Expected columns exist in output | Wrong column names or dropped columns |
| groupby row count = unique values of group column | Aggregation correctness |
| Top N output rows ≤ N | top_n tool working correctly |
| Date filtered output within specified range | date_filter correctness |
| Numeric aggregated columns are actually numeric | Type integrity after groupby |

**Output:** `{"status": "pass"}` or `{"status": "fail", "check": str, "reason": str}`

---

### 6. Loop Controller

**Purpose:** Orchestrates retries, replanning, and exit conditions. Prevents infinite loops and manages the system's error recovery behaviour.

**Boundaries:**
- **Per-step retry limit:** 2 retries per step (3 total attempts)
- **Total execution cap:** `len(plan) × 2` — dynamic, scales with plan size

**Retry Logic:**

```
Step fails (tool error or critic fail)
    ↓
fix_params called → [STUB: currently returns step unchanged]
    ↓
Retry step (up to 2 times)
    ↓
If still failing after 2 retries → call replanner
    ↓
replan → [STUB: currently returns error]
    ↓
Return partial trace + explanation
```

> **Note:** `fix_params` and `replan` are currently stubs. Retries re-run the identical step parameters. LLM-based parameter correction is the planned next implementation step.

**Exit Conditions:**
- Step fails after 2 retries and replan also fails → stop, return partial result + explanation
- Total executions exceed `len(plan) × 2` → stop with cap-exceeded message

**Key Design Decision:** A failed step is never skipped. Downstream steps depend on its state store output — skipping would corrupt the entire pipeline.

---

### 7. Answer Generator

**Purpose:** Narrates the final computed DataFrame in plain English.

**When it runs:** Once, after the loop completes successfully — outside the loop.

**Model:** `llama-3.1-8b-instant` via Groq API — temperature=0.3, max_tokens=256

**Input:** Original user query + final DataFrame (always small post-aggregation)

**Output:** `{"status": "success", "answer": str}` or `{"status": "error", "message": str}`

**Key Design Decision:** Answer Generator failure is non-critical — the pipeline returns the DataFrame regardless. The LLM narrates computed data only, so there is no hallucination risk on numbers.

---

### 8. Observability

**Purpose:** Log every decision the system makes so the full execution can be reconstructed and debugged.

**Every log entry carries:**
- `run_id` — unique 8-char identifier linking all log entries for one query run
- `timestamp` — when this event occurred

**Logging Points:**

| Point | Core Content |
|---|---|
| Query received | query text |
| Schema generator | column count, column names |
| Planner | step count, plan summary (tool chain) |
| Tool call started | tool name, input shape, parameters |
| Tool call completed | status, message, output shape |
| Step executed | step, tool, status, critic verdict, output shape |
| Answer generator | answer text or error |
| Pipeline complete / error | status, total executions, steps in plan |

**Log files:** `logs/run_YYYY_MM_DD_HH_MM_SS.log` — one per pipeline run. Console shows compact one-liners; file shows expanded detail.

---

## Build Status

| Component | File | Status |
|---|---|---|
| Tool Layer (9 tools) | `src/tools/*.py` | Done |
| TOOL_REGISTRY | `src/tools/tools.py` | Done |
| Schema Generator | `src/core/schema_gen.py` | Done |
| Planner (LLM) | `src/core/planner.py` | Done |
| Executor + State Store | `src/core/executor.py` | Done |
| Rule-Based Critic | `src/critics/rule_based_critic.py` | Done |
| Loop Controller | `src/core/loop_controller.py` | Done |
| Answer Generator | `src/core/answer_generator.py` | Done |
| Observability / Logging | `src/utils/logger.py` | Done |
| Pipeline | `src/core/pipeline.py` | Done |
| Streamlit UI | `app.py` | Done |
| Param Fixer | `src/core/param_fixer.py` | Stub only |
| Replanner | `src/core/replanner.py` | Stub only |
| Evaluation Pipeline | `eval/` | Done |

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python |
| Data operations | Pandas |
| LLM | Groq API — `llama-3.1-8b-instant` |
| Structured output | Pydantic |
| UI | Streamlit |
| Logging | Python logging / plain text .log files |

---

## Streamlit UI Panels

1. **Query input** — natural language question
2. **Answer panel** — LLM-generated plain English answer (shown first)
3. **Result table** — final DataFrame output
4. **Execution trace** — per-step tool, status, critic verdict, output shape
5. **Plan steps** — steps planned by the LLM (tool + parameters + input/output keys)
6. **Schema panel** — condensed schema sent to the Planner

---

## Key Architectural Decisions

| Decision | Choice | Reason |
|---|---|---|
| Free code gen vs predefined tools | Predefined tools | Safer, validatable, debuggable — no black box |
| Tool count | 9 tools | Covers all query types including date extraction, arithmetic, projection, rename |
| groupby + aggregate | Single combined tool | groupby alone returns unusable GroupBy object |
| Critic type | Rule-based only (deterministic) | LLM critic adds latency without reliable signal; rule-based covers all structural failures |
| State store | Dict keyed by step output name | Enables retry from failure point, not from scratch |
| Retry limits | 2 retries + 1 replan + dynamic cap (`len(plan) × 2`) | Prevents infinite loops while allowing self-correction |
| Schema passed to Planner | Condensed (dtype + min/max + sample values) | Fewer tokens; 8B model handles it better |
| Parameter validation | `inspect.signature()` against real tool functions | Catches missing/unknown params before Executor runs |
| State store scope | Internal to Executor, not returned in output | Trace (shape + columns) is sufficient for debugging — raw dfs are heavy |
| Quarter filtering | `extract_date_part` → `filter_by_condition` | `date_filter` uses lookback — not suited for fixed calendar quarters |

---

## Failure Modes

| Failure | How Triggered | Expected Behaviour |
|---|---|---|
| Wrong column name in plan | Ambiguous query | Rule-based critic catches; retry re-runs (param fixer is stub) |
| Empty result after filter | Over-specific filter | Critic catches empty df; retry re-runs |
| Ambiguous time reference | "recent sales" with no date | Planner uses dataset max date as end_date |
| Max retries exceeded | Repeatedly wrong parameters | Loop controller stops, returns partial trace + explanation |
| Unsolvable query | Query needs tools not available | Planner returns `{"status": "unsolvable", "reason": "..."}` |

---

## Evaluation Pipeline

**Run:** `python eval/run_eval.py`

30 queries with manually written ground truth, organized into 6 groups covering every reasoning type the pipeline handles:

| Group | Reasoning Type | Queries |
|---|---|---|
| 1 | Simple Aggregation | Q01–Q05 |
| 2 | Filtering | Q06–Q10 |
| 3 | Grouping + Ranking | Q11–Q15 |
| 4 | Time Based | Q16–Q20 |
| 5 | Multi Condition | Q21–Q25 |
| 6 | Derived Calculations (shipping time) | Q26–Q30 |

**Ground truth:** Pure pandas functions per query — no LLM, deterministic, manually verified.

**Comparison modes (per query):**
- `value_only` — extracts all numeric cell values, sorts and compares with 1% float tolerance. Used when pipeline output column naming is unpredictable (scalar results, derived columns).
- `full` — shape + column set + sort-then-compare cell values. Used for multi-row unordered results.
- `ordered` — shape + column set + positional row comparison. Used for ranked/top-N results where row order encodes rank.

**Metrics reported:**
- Pipeline success rate (did it produce a result?)
- Value match rate (are the numbers correct?)
- Full match rate (shape + columns + values)
- Avg retries and avg executions per query
- Per-group breakdown across all 6 groups

**Output:** JSON + CSV + text report saved to `eval/results/` with timestamp.
