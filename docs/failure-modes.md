# Failure Modes

## Handled Failures

These are caught and recovered by the pipeline automatically.

| Failure | How Triggered | What Happens |
|---|---|---|
| Wrong column name in plan | Ambiguous query maps to wrong column | Rule-based critic catches; Param Fixer (LLM) corrects parameters and step is retried |
| Empty result after filter | Over-specific filter removes all rows | Critic catches empty df; step retried with corrected parameters |
| Ambiguous time reference | "recent sales" with no date anchor | Planner uses dataset max date as `end_date` — safe default, no hallucination |
| Max retries exceeded | Repeatedly wrong parameters | Replanner (LLM) generates a new plan from scratch; if that also fails, pipeline returns partial trace + explanation |
| Unsolvable query | Query needs tools that don't exist, or is genuinely compound (two separate pipeline plans needed) | Planner returns `{"status": "unsolvable", "reason": "..."}` — no partial plan generated |
| Answer Generator failure | LLM narration fails or times out | Pipeline returns DataFrame regardless — narration is non-critical. A deterministic fallback string is built from `final_df` instead of returning `None`. |
| Planner API failure | Groq API error or timeout | Planner retries once; returns `{"status": "error"}` if retry also fails |
| Pydantic validation failure | LLM returns malformed plan JSON | Planner retries once with the validation error injected into the prompt |

---

## Known Limitations

| Limitation | Description |
|---|---|
| Wrong sort order | "worst performing" may produce ascending instead of descending. Planner quality is the only guard — no post-hoc check. |
| Single filter per step | `filter_by_condition` applies one condition at a time. Multi-condition queries require multiple sequential filter steps. |
| No fuzzy column matching | Column names must match schema exactly. Planner is prompted to use exact schema column names. |
| No multi-value filter | `filter_by_condition` supports only one value + one operator (no `isin`). Queries like "show years X, Y, Z" can cause the planner to return `unsolvable` instead of using `groupby_aggregate`. |
| Answer generator arithmetic hallucination | When the pipeline returns a multi-row DataFrame and the answer generator must sum or re-aggregate values, it produces wrong numbers. Observed in eval: reported $763K vs actual $286K (Q41), picked one cell as a region total instead of summing across rows (Q43). The answer generator is only reliable when restating values already present in the result. |
| 4-turn context resolution | Multi-turn follow-ups work for 2-turn and 3-turn conversations (100% accuracy). 4-turn cases where context must be traced through a chain of prior questions fail consistently — the model cherry-picks from the context window rather than following the conversation sequence. |
| Answer generator has no session context | `recent_questions` feeds the planner only. The answer generator sees only `final_df` + the current query — it cannot use prior questions to disambiguate what to highlight in the response. |

---

## Retry + Replan Flow

```
Step fails (critic returns "fail")
    ↓
Param Fixer (LLM) — receives failed step, error, critic check, query, schema
    ↓
Returns corrected parameters
    ↓
Retry (attempt 2)
    ↓
[still fails]
    ↓
Retry (attempt 3)
    ↓
[still fails — all retries exhausted]
    ↓
Replanner (LLM) — generates a completely new plan from original_df
    ↓
[new plan succeeds] → continue execution
[new plan fails]    → return partial trace + explanation
```

Per-step cap: 3 total attempts (1 original + 2 retries). Max replan attempts: 1. Global cap: `len(plan) × 2` total executions across all steps.

---

## Critic Failure Codes

When the critic fails a step, it returns one of these `check` values:

| Check Name | Meaning |
|---|---|
| `not_none` | Tool returned None — silent crash |
| `not_empty` | Result DataFrame has 0 rows |
| `no_fully_empty_columns` | At least one column has all nulls |
| `expected_columns_present` | A required column is missing from the result |
| `groupby_row_count` | Row count ≠ number of unique group values |
| `top_n_row_count` | Result has more rows than N |
| `date_filter_range` | At least one date falls outside the requested range |
| `numeric_agg_columns` | Aggregated column is not numeric |

---

## What Is Not Caught

- **Semantic correctness** — the critic checks structure, not meaning. A plan that computes the wrong metric (e.g. `mean` instead of `sum`) will pass all critic checks.
- **Wrong sort direction** — sorting ascending when the query says "worst" is not a structural failure and passes the critic.
- **Incorrect grouping key** — grouping by the wrong column produces a valid DataFrame and passes all checks.
- **Superset results** — returning all groups instead of filtering to the requested subset (e.g. all 4 regions instead of the 2 being compared) passes the critic. The answer generator usually compensates correctly.

These cases rely entirely on Planner quality (model temperature=0.0, precise system prompt).
