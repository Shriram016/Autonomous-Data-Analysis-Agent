# Autonomous Data Analysis Agent (ADAA)

A deterministic AI pipeline that takes a natural language question about a dataset and returns a **verified, computed answer with a full reasoning trace** — not a chatbot response.

Every step is planned, executed through predefined tools, validated by a rule-based critic, and logged. The system never generates free-form code.

---

## Evaluation Results

Tested on **30 queries** across 6 reasoning groups using the Sample Superstore dataset:

| Metric | Result |
|---|---|
| Pipeline success | 30/30 (100%) |
| Value match (primary) | 28/30 (93%) |
| Full match (shape + columns + values) | 28/30 (93%) |
| Avg executions per query | 2.5 |

| Group | Reasoning Type | Accuracy |
|---|---|---|
| Group 1 | Simple Aggregation | 100% |
| Group 2 | Filtering | 80% |
| Group 3 | Grouping + Ranking | 100% |
| Group 4 | Time Based | 100% |
| Group 5 | Multi Condition | 80% |
| Group 6 | Derived Calculations (shipping time) | 100% |

---

## Why This Project

- **Verifiable output** — the answer is either correct or not. No hiding behind vague text
- **Full reasoning trace** — every tool call, parameter, and critic verdict is logged
- **Deterministic safety** — no free-form code generation; only predefined tools are called
- **Business relevance** — solves a real analytical problem any company faces

---

## Getting Started

**Prerequisites:** Python 3.9+, a [Groq API key](https://console.groq.com/)

```bash
# 1. Clone the repository
git clone <repo-url>
cd adaa

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up your API key
echo "GROQ_API_KEY=your_key_here" > .env

# 4. Launch the Streamlit UI
streamlit run app.py

# 5. (Optional) Run the evaluation pipeline
python eval/run_eval.py

# Run only the first N queries
python eval/run_eval.py --limit 5
```

---

## Dataset

**Sample Superstore Dataset**
- Source: [Kaggle](https://www.kaggle.com/datasets/vivek468/superstore-dataset-final)
- Rows: ~9,994 | Columns: 21

Key columns: `Order Date`, `Ship Date`, `Ship Mode`, `Category`, `Sub-Category`, `Sales`, `Quantity`, `Discount`, `Profit`, `Customer Name`, `State`, `Region`, `Segment`

---

## System Architecture

```
User Query
    ↓
Schema Generator          → Converts raw dataset → concise JSON schema (never the raw df)
    ↓
Planner (LLM)             → Query + schema → structured JSON execution plan
    ↓
┌──────────────────────────────────────────────┐
│  Loop Controller                             │
│  ┌────────────────────────────────────────┐  │
│  │ Executor                               │  │
│  │     ↓                                  │  │
│  │ Tool Layer  (10 predefined functions)  │  │
│  │     ↓                                  │  │
│  │ Rule-Based Critic  (8 deterministic    │  │
│  │                     checks per step)   │  │
│  │     ↓  pass / retry / replan           │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
    ↓
Answer Generator (LLM)    → Narrates the result DataFrame in plain English
    ↓
Final Answer + Reasoning Trace
```

---

## Components

### Schema Generator
Converts the raw 9,994-row DataFrame into a concise JSON description safe to pass to an LLM. Captures dtype, min/max, median (numeric), sample values for low-cardinality columns, and date range.

```json
{
  "Order Date": {"dtype": "datetime64[ns]", "min": "2021-01-01", "max": "2024-12-31"},
  "Category":   {"dtype": "object", "unique_count": 3, "sample_values": ["Furniture", "Technology", "Office Supplies"]},
  "Sales":      {"dtype": "float64", "min": 0.44, "max": 22638.48, "median": 54.49}
}
```

---

### Planner (LLM)
Converts a natural language query into a validated, step-by-step JSON execution plan.

- **Model:** `qwen/qwen3-32b` via Groq API — temperature 0.0, deterministic output
- **Validation:** Two layers — Pydantic (structure) + business logic checks (tool names, parameters, state store chain)
- **Retry:** Re-calls LLM once with the validation error injected if the plan fails checks

**Example plan for "Top 10 customers by sales in last 3 months":**
```json
{
  "status": "success",
  "plan": [
    {"step": 1, "tool": "date_filter",       "parameters": {"col_name": "Order Date", "time_period": "3M", "end_date": "2024-12-31"}, "input": "original_df",    "output": "step_1_output"},
    {"step": 2, "tool": "groupby_aggregate", "parameters": {"group_col": "Customer Name", "agg_col": {"Sales": "sum"}},               "input": "step_1_output", "output": "step_2_output"},
    {"step": 3, "tool": "sort",              "parameters": {"sort_col": {"Sales_sum": "desc"}},                                        "input": "step_2_output", "output": "step_3_output"},
    {"step": 4, "tool": "top_n",             "parameters": {"N": 10},                                                                  "input": "step_3_output", "output": "step_4_output"}
  ]
}
```

---

### Tool Layer
10 predefined, callable functions. The LLM selects tools and specifies parameters — it never writes pandas code.

| Tool | Purpose |
|---|---|
| `date_filter` | Filter rows within a lookback date range ending at a given date |
| `filter_by_condition` | Filter rows by a single column value (`==`, `!=`, `>`, `>=`, `<`, `<=`) |
| `extract_date_part` | Extract month / year / quarter / day into a new column |
| `column_arithmetic` | Arithmetic between two columns; supports datetime subtraction (result = days) |
| `groupby_aggregate` | Group by one or more columns and aggregate (sum, mean, count, min, max, median, std) |
| `aggregate_column` | Single aggregate value over the whole dataset — no grouping; returns 1-row result |
| `sort` | Sort by one or more columns (ascending or descending) |
| `top_n` | Return the first N rows (always preceded by sort) |
| `select_columns` | Keep only specified columns, drop the rest |
| `rename_column` | Rename columns via a mapping |

All tools return: `{"status": "success|error", "message": "...", "result": <DataFrame or None>}`

**Key design decision:** `groupby` and `aggregate` are a single combined tool — `groupby` alone returns an unusable GroupBy object, never a DataFrame.

---

### Executor
Reads each step from the plan, calls the correct tool, and manages intermediate outputs in a state store.

```
state_store = {
  "original_df":   <full dataset>,
  "step_1_output": <df after step 1>,
  "step_2_output": <df after step 2>,
  ...
}
```

A failed step is never skipped — downstream steps depend on its output.

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

### Loop Controller
Orchestrates retries and exit conditions. Prevents infinite loops while allowing self-correction.

- **Per-step retry limit:** 2 retries (3 total attempts per step)
- **Total execution cap:** `len(plan) × 2` — scales dynamically with plan size
- **Exit:** Returns partial trace + explanation if all retries are exhausted

---

### Answer Generator
Narrates the final computed DataFrame in plain English.

- **Model:** `qwen/qwen3-32b` via Groq API — temperature 0.3
- Runs once, after the loop completes — outside the retry loop
- Failure is non-critical: pipeline returns the DataFrame regardless

---

### Observability
One log file per run (`logs/run_YYYY_MM_DD_HH_MM_SS.log`), with a unique `run_id` linking every event for that query.

| Logged Event | What It Captures |
|---|---|
| Schema generated | Column count, column names |
| Plan received | Tool chain, step count |
| Tool call started | Tool name, input shape, parameters |
| Tool call completed | Status, output shape, message |
| Step executed | Tool, status, critic verdict, output shape |
| Answer generated | Final narrative or error |
| Pipeline complete | Status, total executions, plan step count |

---

## Evaluation Pipeline

**30 queries** with manually written ground truth, organized into 6 groups:

| Group | Reasoning Type | Queries |
|---|---|---|
| 1 | Simple Aggregation | Q01–Q05 |
| 2 | Filtering | Q06–Q10 |
| 3 | Grouping + Ranking | Q11–Q15 |
| 4 | Time Based | Q16–Q20 |
| 5 | Multi Condition | Q21–Q25 |
| 6 | Derived Calculations (shipping time) | Q26–Q30 |

**Ground truth:** Pure pandas functions per query — no LLM, deterministic, manually verified.

**Comparison modes:**
- `value_only` — extracts all numeric values, sorts, and compares within 1% float tolerance
- `full` — shape + column set + sort-then-compare values
- `ordered` — shape + column set + positional comparison (for ranked results where order = rank)

**Output:** JSON + CSV + text report saved to `eval/results/` with timestamp.

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python |
| Data operations | Pandas |
| LLM | Groq API — `qwen/qwen3-32b` |
| Structured output | Pydantic |
| UI | Streamlit |
| Logging | Python `logging` — console + per-run `.log` files |

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Predefined tools vs free code generation | Predefined tools | Safe, validatable, debuggable — no black box |
| Critic type | Rule-based only (deterministic) | LLM critic adds latency without reliable signal |
| State store | Dict keyed by step output name | Enables retry from the failure point, not from scratch |
| Retry limits | 2 retries + dynamic cap (`len(plan) × 2`) | Prevents infinite loops while allowing self-correction |
| Schema passed to Planner | Condensed (dtype + min/max + sample values) | Fewer tokens; model handles narrow structured tasks better |
| Quarter filtering | `extract_date_part` → `filter_by_condition` | `date_filter` uses lookback windows — not suitable for fixed calendar quarters |
| groupby + aggregate | Single combined tool | `groupby` alone returns an unusable GroupBy object, never a DataFrame |
| Answer Generator failure | Non-critical — pipeline returns DataFrame regardless | Narration is supplementary; computed data is the primary output |

---

## Failure Modes

| Failure | How Triggered | Behaviour |
|---|---|---|
| Wrong column name in plan | Ambiguous query | Rule-based critic catches; step retried |
| Empty result after filter | Over-specific filter | Critic catches empty df; step retried |
| Ambiguous time reference | "recent sales" with no date | Planner uses dataset max date as `end_date` |
| Max retries exceeded | Repeatedly wrong parameters | Loop controller stops, returns partial trace + explanation |
| Unsolvable query | Query needs unavailable tools | Planner returns `{"status": "unsolvable", "reason": "..."}` — no partial plan |
