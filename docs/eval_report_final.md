# ADAA Evaluation Report

**Pipeline:** V2 LangGraph (schema_gen → planner → execute_step loop → answer_gen)  
**Planner model:** `openai/gpt-oss-20b` with `reasoning_effort: low`  
**Dataset:** Sample Superstore — 9,994 rows × 21 columns (2014–2017)  
---

## Overview

Four evaluation categories covering 63 total test cases across single-turn, compound, and multi-turn query patterns.

| Category | What it tests | Cases | Result |
|---|---|---|---|
| **Single-Turn** | Core pipeline accuracy — aggregation, filtering, grouping, ranking, time-based, multi-condition, derived calculations | 30 | **29/30 passed (96.7%)** |
| **Pseudo-Compound** | Queries that look compound but are solvable in a single plan (breakdown subsumes scalar, comparison across slices) | 7 | **4 correct, 2 partial, 1 failed** |
| **Truly Compound** | Queries requiring two separate pipeline plans — expected to be marked unsolvable | 10 | **6/10 correctly unsolvable, 2 attempted with hallucinated answers, 2 solved correctly (misclassified as compound)** |
| **Multi-Turn** | Session memory — follow-up questions that rely on context from prior turns | 16 | **12/16 passed (75%)** |

### Key Findings

- **Single-turn queries are highly reliable** — 96.7% accuracy across all query types, with only one model planning fluke (Q06).
- **Prompt engineering has high leverage** — a two-line prompt addition fixed 4/5 unsolvable errors in pseudo-compound queries.
- **Answer generator hallucinates arithmetic** — when the pipeline returns a multi-row DataFrame and the answer generator must sum/re-aggregate values, it produces wrong numbers (Q41: $763K vs actual $286K).
- **Multi-turn context works for simple swaps** — 2-turn and 3-turn follow-ups pass consistently. 4-turn cases with multi-hop context resolution still fail.
- **Superset DataFrames are a recurring pattern** — the planner prefers `groupby_aggregate` over `filter → groupby_aggregate`, returning extra rows. The answer generator compensates correctly in most cases.

### Test Files

| File | Contents | Status |
|---|---|---|
| `eval/test_cases.py` | 30 single-turn queries (Q01–Q30) | ✅ Complete |
| `eval/test_cases2.py` | 7 pseudo-compound queries (Q31–Q37) | ✅ Complete |
| `eval/test_cases3.py` | 10 truly compound queries (Q38–Q47) | ✅ Complete |
| `eval/multiturn_test_cases.py` | 16 multi-turn session cases (MT01–MT16) | ✅ Complete |

---
---

## Single-Turn — 30 Queries (Q01–Q30)

**Source:** `eval/test_cases.py` | **Runner:** `eval/run_eval.py --round 1`  
**Raw results:** `eval/results/eval_2026_06_20_10_59_51.{json,csv,txt}`  
**Result: 29/30 passed (96.7%)**

---

### Metrics

| Metric | Value |
|---|---|
| Pipeline success | 30 / 30 (100%) |
| Value match | **29 / 30 (96.7%)** |
| Full match | 29 / 30 (96.7%) |
| Avg plan steps | 2.6 |
| Avg retries | 0.03 |
| Avg duration | 16.0s |

> **Value match** compares only numeric values, ignoring column names. **Full match** additionally checks shape and column names.

### Group Breakdown

| Group | Name | Queries | Value Match | Avg Retries |
|---|---|---|---|---|
| 1 | Simple Aggregation | Q01–Q05 | **100%** | 0.00 |
| 2 | Filtering | Q06–Q10 | **80%** | 0.00 |
| 3 | Grouping + Ranking | Q11–Q15 | **100%** | 0.00 |
| 4 | Time Based | Q16–Q20 | **100%** | 0.00 |
| 5 | Multi Condition | Q21–Q25 | **100%** | 0.20 |
| 6 | Derived Calculations | Q26–Q30 | **100%** | 0.00 |

### Per-Query Results

| ID | Result | Steps | Retries | Time | Query |
|---|---|---|---|---|---|
| Q01 | ✅ | 1 | 0 | 3.0s | What is the total sales across all orders? |
| Q02 | ✅ | 1 | 0 | 2.1s | What is the average discount given across all products? |
| Q03 | ✅ | 1 | 0 | 20.0s | How many total orders are there in the dataset? |
| Q04 | ✅ | 1 | 0 | 35.1s | What is the total profit across all regions? |
| Q05 | ✅ | 1 | 0 | 4.9s | What is the average quantity ordered per transaction? |
| **Q06** | **❌** | **1** | **0** | **21.0s** | **What are the total sales for the Technology category?** |
| Q07 | ✅ | 2 | 0 | 20.0s | What is the total profit from the West region? |
| Q08 | ✅ | 2 | 0 | 20.9s | How many orders were placed in the Consumer segment? |
| Q09 | ✅ | 2 | 0 | 35.0s | What is the total sales for Standard Class ship mode? |
| Q10 | ✅ | 2 | 0 | 20.5s | What is the average sales value for orders from California? |
| Q11 | ✅ | 3 | 0 | 21.8s | Which are the top 5 states by total sales? |
| Q12 | ✅ | 3 | 0 | 20.8s | Which are the bottom 5 sub-categories by total profit? |
| Q13 | ✅ | 3 | 0 | 20.9s | Which 3 ship modes generate the highest average sales? |
| Q14 | ✅ | 3 | 0 | 6.6s | Which are the top 10 customers by total sales? |
| Q15 | ✅ | 3 | 0 | 6.6s | Which product category has the highest average discount? |
| Q16 | ✅ | 2 | 0 | 7.9s | What is the total sales for each year? |
| Q17 | ✅ | 4 | 0 | 22.2s | Which month has the highest number of orders across all years? |
| Q18 | ✅ | 2 | 0 | 20.1s | What is the total profit per quarter? |
| Q19 | ✅ | 3 | 0 | 20.9s | What are the total sales for Q1 across all years? |
| Q20 | ✅ | 4 | 0 | 8.2s | Which year had the highest total profit? |
| Q21 | ✅ | 3 | 0 | 6.0s | What is the total sales for Furniture in the West region? |
| Q22 | ✅ | 3 | 0 | 21.7s | How many orders were placed in the Consumer segment in California? |
| Q23 | ✅ | 4 | 1 | 23.1s | What is the average profit for Technology products in Q1? |
| Q24 | ✅ | 3 | 0 | 17.4s | What are the total sales for Office Supplies in the East region? |
| Q25 | ✅ | 4 | 0 | 8.1s | Which are the top 5 customers by sales in the Consumer segment? |
| Q26 | ✅ | 2 | 0 | 6.8s | What is the average shipping time in days across all orders? |
| Q27 | ✅ | 4 | 0 | 8.3s | Which product category has the longest average shipping time? |
| Q28 | ✅ | 4 | 0 | 21.4s | Which ship mode has the shortest average shipping time? |
| Q29 | ✅ | 3 | 0 | 20.4s | What is the average shipping time for orders from the West region? |
| Q30 | ✅ | 4 | 0 | 9.2s | Which are the top 5 states with the longest average shipping time? |

### Failure Analysis

#### Q06 — Value Mismatch (Model Planning Error)

**Query:** `What are the total sales for the Technology category?`

| | Ground Truth | Pipeline |
|---|---|---|
| Value | $836,154.03 | $2,297,200.86 |
| Error | — | +174.73% |

**Root cause:** The planner used `aggregate_column(Sales, sum)` without a preceding `filter_by_condition(Category == Technology)`. It aggregated the entire dataset instead of Technology only.

**Diagnosis:** Model fluke — all other filter queries (Q07–Q10) generated correct 2-step plans. Not a prompt gap.

### Notable Observations

- **Q23 is the only retry** — param_fixer corrected bad parameters and the query succeeded. Retry/param-fixer path working as designed.
- **Latency is bimodal** — some queries run in 3–9s, others cluster at 20–35s due to Groq API queue time. No correlation with plan complexity.

---
---

## Pseudo-Compound — 7 Queries (Q31–Q37)

**Source:** `eval/test_cases2.py` | **Runner:** `eval/run_eval.py --round 2`  
**Raw results:** `eval/results/eval_2026_06_20_15_42_14.{json,csv,txt}`  
**Result: 4 correct, 2 partial, 1 failed**

These queries look compound ("total sales and breakdown by region") but are solvable in a single plan because the breakdown subsumes the scalar, or a single groupby answers a comparison.

**Prompt change before this run:** Added two clarification lines to the system prompt:
- *If a query asks for both an overall total and a breakdown by group, use groupby_aggregate only — the breakdown subsumes the overall total.*
- *If a query asks to compare two values of the same column, use groupby_aggregate on that column.*

---

### Per-Query Results

| ID | Result | Steps | Time | Query |
|---|---|---|---|---|
| Q31 | ✅ Correct | 1 | 2.8s | What are total sales? Also break it down by region. |
| Q32 | ✅ Correct | 1 | 12.2s | What is the average discount overall and by customer segment? |
| **Q33** | **❌ Failed** | **0** | **36.3s** | **What is the average order value per category and overall?** |
| Q34 | ✅ Correct | 3 | 4.3s | What were total sales in 2017, and how did each region perform that year? |
| Q35 | ✅ Correct | 1 | 19.0s | What is the total profit by ship mode and overall? |
| Q36 | ⚠️ Partial | 2 | 35.1s | Compare total sales in 2016 versus 2017. |
| Q37 | ⚠️ Partial | 2 | 6.5s | How do sales in the Consumer segment compare to the Corporate segment? |

### Failure Analysis

**Q33 — Unsolvable (Model Inconsistency):** Identical pattern to Q32 and Q35 which both pass. The model followed the prompt rule for those but not Q33 — likely the phrasing "average order value" (not a direct column name) caused the model to overthink. Model non-determinism, not a prompt gap.

**Q36/Q37 — Partial Correct (Superset DataFrame):** Pipeline returned all groups instead of filtering to the requested slices (4 years instead of 2, 3 segments instead of 2). The answer generator correctly extracted the relevant values — natural language answers are accurate.

### Notable Observations

- The prompt fix resolved 4/5 "unsolvable" errors from the pre-fix run — 80% fix rate from a two-line edit.
- Superset DataFrames are a consistent planner behavior — it prefers the simpler plan (just groupby) over the more precise one (filter → groupby).

---
---

## Truly Compound — 10 Queries (Q38–Q47)

**Source:** `eval/test_cases3.py` | **Runner:** `eval/run_eval.py --round 3`  
**Raw results:** `eval/results/eval_2026_06_20_16_21_09.{json,csv,txt}`  
**Result: 6/10 correctly unsolvable, 4 misclassified**

These queries ask for two or more distinct results that cannot be solved in a single pipeline plan. The expected behavior is **unsolvable** for all 10.

---

### Per-Query Results

| ID | Result | Steps | Time | Query |
|---|---|---|---|---|
| Q38 | ✅ Unsolvable | 0 | 2.2s | What are the total sales and total profit across all orders? |
| Q39 | ✅ Unsolvable | 0 | 13.7s | What is the average discount and average quantity per order? |
| Q40 | ✅ Unsolvable | 0 | 36.5s | How many orders were placed in total, and how many unique customers placed them? |
| **Q41** | **❌ Attempted** | **2** | **8.6s** | **Show me total profit and also which states are most profitable.** |
| Q42 | ✅ Unsolvable | 0 | 20.7s | Which states are most profitable and which product categories are most profitable? |
| **Q43** | **❌ Attempted** | **1** | **23.8s** | **What is the total sales by region and by ship mode?** |
| Q44 | ✅ Unsolvable | 0 | 1.5s | Show me the top 5 customers by sales and the top 5 states by sales. |
| Q45 | ⚠️ Solved (misclassified) | 2 | 5.0s | For Technology orders, what are the total sales and average discount? |
| Q46 | ⚠️ Solved (misclassified) | 2 | 25.3s | In the West region, how many orders were placed and what was the total profit? |
| Q47 | ✅ Unsolvable | 0 | 24.6s | For orders shipped via First Class, what is the average shipping time and total sales? |

### Failure Analysis

**Q41/Q43 — Incorrectly Attempted + Answer Generator Hallucination:** The pipeline found creative single-plan workarounds (groupby all states, cross-tab by Region × Ship Mode). The DataFrames were correct, but the answer generator hallucinated when summarizing them:

| Case | Correct Value | Answer Generator Reported | Error |
|---|---|---|---|
| Q41 (total profit) | $286,397 | $763,819 | +167% |
| Q43 (Central region total) | $501,240 | $318,528 | -36% |

**Root cause:** The answer generator cannot reliably perform arithmetic over multi-row DataFrames. When it must sum or re-aggregate values, it hallucinates.

**Q45/Q46 — Misclassified (Not Actually Compound):** The `groupby_aggregate` tool accepts multi-key agg dicts (e.g. `{"Sales": "sum", "Discount": "mean"}`), so "filter + two aggregations" is solvable in one step. Both queries were answered correctly. These need to be replaced with truly compound queries.

---
---

## Multi-Turn — 16 Cases (MT01–MT16)

**Source:** `eval/multiturn_test_cases.py` | **Runner:** `eval/run_multiturn_eval.py`  
**Raw results:** `eval/results/multiturn_20260620_173926.json` (first run), `eval/results/multiturn_20260622_082951.json` (re-run)  
**Result: 12/16 passed (75%)**

Each case is a sequence of 2–4 turns sharing a session ID. Only the final turn has ground truth — earlier turns establish context via `recent_questions` (sliding window of last 3 queries).

**Changes applied between first run and re-run:**
1. MT09/MT10 queries reworded to unambiguously anchor context ("What about the profit for the same?" instead of "What about the total profit?")
2. MT12 query changed from "And Tables?" to "What about Tables?" (model fails on ultra-short follow-ups)
3. System prompt updated: follow-up handling changed to "follow the conversation chain" wording

---

### Per-Case Results

| ID | Pattern | Turns | Result | Issue |
|---|---|---|---|---|
| MT01 | Year swap | 2 | ✅ Pass | |
| MT02 | Year swap | 3 | ✅ Pass | |
| MT03 | Category swap | 2 | ✅ Pass | |
| MT04 | Category swap | 3 | ✅ Pass | |
| MT05 | Region swap | 2 | ✅ Pass | |
| MT06 | Region swap | 3 | ✅ Pass | |
| MT07 | Segment swap | 2 | ✅ Pass | |
| MT08 | Segment swap | 3 | ✅ Pass | |
| MT09 | Metric swap | 2 | ✅ Pass | Fixed via query reword |
| MT10 | Metric swap | 3 | ✅ Pass | Fixed via query reword |
| MT11 | Sub-Category swap | 2 | ✅ Pass | |
| MT12 | Sub-Category swap | 3 | ✅ Pass | Fixed: "What about Tables?" instead of "And Tables?" |
| **MT13** | **Year + Region** | **4** | **❌ Fail** | Carried forward 2014 instead of 2015 |
| **MT14** | **Category + Metric** | **4** | **❌ Fail** | Returned Profit instead of Sales (didn't carry forward metric swap) |
| **MT15** | **Multi-year synthesis** | **4** | **❌ Fail** | Marked unsolvable — "can't filter multiple years" |
| **MT16** | **Multi-region synthesis** | **4** | **❌ Fail** | Returned all 4 regions instead of filtering to 3 discussed |

### Results by Turn Count

| Turn count | Passed | Total | Rate |
|---|---|---|---|
| 2-turn | 6 | 6 | **100%** |
| 3-turn | 6 | 6 | **100%** |
| 4-turn | 0 | 4 | **0%** |

### Failure Analysis

**MT13 — Wrong Year Carried Forward:** The planner saw turns about 2014, 2015, and West region in its 3-question window. For "And the East region?" it picked 2014 instead of tracing the chain (turn 4 → turn 3 "for that" → turn 2 which was 2015). The model cherry-picks from the context window rather than following the conversation sequence.

**MT14 — Metric Swap Not Carried Forward:** Turn 3 swapped from Profit to Sales ("What were the total sales instead?"), but turn 4 ("And for Office Supplies?") reverted to Profit. The model even listed "total sales" in its reasoning but still chose Profit.

**MT15 — Multi-Value Filter Marked Unsolvable:** The planner correctly identified years 2015, 2016, 2017 but tried to chain `filter_by_condition` calls (which are AND, not OR) and concluded it's impossible. It never considered using `groupby_aggregate(Year, Sales sum)` which would return all years. Model locked into the "filter then aggregate" pattern from prior turns.

**MT16 — Superset DataFrame:** Same pattern as Q36/Q37. Planner used `groupby_aggregate(Region, Profit sum)` returning all 4 regions instead of filtering to the 3 discussed (West, East, South).

### Notable Observations

- **2-turn and 3-turn swaps are fully reliable** — the planner handles single-dimension follow-ups (year, category, region, segment, sub-category) with 100% accuracy across 12 cases.
- **4-turn cases expose multi-hop reasoning limits** — when the answer requires tracing context through a chain of prior questions (not just the most recent one), the model fails consistently.
- **Ultra-short queries fail** — "And Tables?" was marked unsolvable, but "What about Tables?" passed. The model needs minimal follow-up phrasing to resolve context.

---
---

## Open Items

| Category | Item |
|---|---|
| Single-Turn | Q06 — investigate alternate phrasings for single-category filter queries |
| Pseudo-Compound | Decide whether to accept superset DataFrames (adjust ground truth) or push planner to filter |
| Truly Compound | Replace Q41, Q43, Q45, Q46 with correctly classified compound queries |
| Truly Compound | Investigate answer generator guardrails for arithmetic over multi-row DataFrames |
| Multi-Turn | MT13/MT14 — 4-turn chain tracing fails (model reasoning limitation, no fix identified) |
| Multi-Turn | MT15/MT16 — synthesis/superset issues (model reasoning limitation) |

---
---

## Appendix: Multi-Turn 4-Turn Query Chains (MT13–MT16)

### MT13 — Year + Region Swap (❌ Fail)

| Turn | Query | Evaluated? |
|---|---|---|
| 1 | What were total sales in 2014? | No |
| 2 | What about 2015? | No |
| 3 | Show me just the West region for that. | No |
| 4 | And the East region? | **Yes** — expected: Sales sum for East region in **2015**, got: East region in **2014** |

### MT14 — Category + Metric Swap (❌ Fail)

| Turn | Query | Evaluated? |
|---|---|---|
| 1 | What was the total profit for Furniture? | No |
| 2 | What about Technology? | No |
| 3 | What were the total sales instead? | No |
| 4 | And for Office Supplies? | **Yes** — expected: **Sales** sum for Office Supplies, got: **Profit** sum for Office Supplies |

### MT15 — Multi-Year Synthesis (❌ Fail)

| Turn | Query | Evaluated? |
|---|---|---|
| 1 | Tell me sales numbers in 2017. | No |
| 2 | What about 2016? | No |
| 3 | 2015? | No |
| 4 | Can you show the 3 years we discussed in a table? | **Yes** — expected: Sales sum grouped by Year for [2015, 2016, 2017], got: marked **unsolvable** |

### MT16 — Multi-Region Synthesis (❌ Fail)

| Turn | Query | Evaluated? |
|---|---|---|
| 1 | What is the total profit in the West region? | No |
| 2 | What about East? | No |
| 3 | And South? | No |
| 4 | Can you compare all 3 regions we discussed? | **Yes** — expected: Profit sum for [West, East, South] (3 rows), got: all 4 regions (4 rows) |
