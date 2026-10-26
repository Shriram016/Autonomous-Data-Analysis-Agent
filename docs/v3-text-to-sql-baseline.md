# Text-to-SQL baseline — findings

**Status: DONE (2026-10-26).**

**Question:** Is our method (the LLM fills a form, the semantic layer writes the SQL) better
than the simple method (the LLM writes the SQL itself)?

**Short answer (2026-10-26):** yes. On the same 34 numbers questions and the same right
answers: **our agent 34 / 34, baseline B (with business rules) 21 / 34, baseline A (table
descriptions only) 5 / 34.** Rules written in a prompt are not followed every time; rules in
the semantic layer are applied in code every time.

Decisions: §0 of [v3-problem-statement.md](v3-problem-statement.md), M2 step 3.

## Setup

| Item | Value |
|---|---|
| Model | Claude Haiku 5.5 for both methods (only the method changes) |
| Library | None (no LangChain SQL agent, no Vanna) |
| Baseline output | `{sql}` or `{cannot_answer}`, structured output |
| Safety | Only SELECT / WITH runs, as `adaa_query` (read-only, 5 s limit) |
| Retry | None (a simple baseline) |
| "Today" | 2018-08-31, the same data date as our agent |
| Variant A | Table descriptions only (tables, columns, types, keys, how they connect) |
| Variant B | Variant A + a short list of business rules (`rules.md`) |
| Cases | The eval's 34 numbers cases (27 answerable, 3 must-stop, 4 examples), cases v4 |
| Right answers | The hand-written SQL of each case, run again for raw values |
| Our results | `eval/results/2026-10-26_110719.json` (the latest eval run) |

**Scoring rules:** values are compared, not column names; numbers exactly (money, counts) or
within 0.01 % (long decimals); a rate counts as right as 0.0677 or 6.77; rows in any order
unless the question asks for a sort; a quarter as `2017-Q2` or `2017-04-01`; a comparison
is right when both period values appear; a must-stop case is right only with
`cannot_answer`; an SQL error or a timeout is wrong.

## Results — run 2026-10-26

| Method | Correct | Cost | Time (p50) |
|---|---|---|---|
| **Our agent** | **34 / 34** | $0.0367 for 44 questions (router included) | 3.8 s |
| Baseline B | 21 / 34 | $0.0140 for both variants, 68 calls | 1.8 s |
| Baseline A | 5 / 34 | (included above) | 1.8 s |

Files: `backend/experiments/text_to_sql/results/2026-10-26_114840.json` (raw answers),
`…_scores.json` (pass / fail), `…_review.md` (one block per case, disagreements first).

## What went wrong in the baseline

**Variant A** misses the business rules almost everywhere:
- Revenue includes freight: R$ 15.8M instead of R$ 13.2M.
- Customers counted by `customer_id`: 99,441 instead of 93,358 people.
- Orders in every status instead of delivered orders only.

**Variant B** has the rules in its prompt and still fails 13 cases:
- It often ignores "delivered orders only": orders in March 2018, card payments, orders in
  the last 3 months.
- It never stops: it answers "late delivery rate by order status" and "cancellation rate by
  order status" instead of refusing them (2 must-stop cases).
- A different repeat-customer reading (3.12 %, every status, instead of 3.00 %).

**Both variants are faster and cheaper per question.** Ours makes 3 calls (router, plan,
answer sentence) and returns more: a table, a chart, "how I got this", support counts.

## Honest limit

Our hand-written right answers follow our own definitions (for example "orders are counted
through their items"). So the SQL is independent of our compiler, but **not of our
definitions**: if a definition is a poor choice, the right answer has the same choice. In
about 4 cases the baseline may be closer to what a manager expects. Even if all 4 go to the
baseline, it reaches about 25 / 34, so the verdict holds.

## Definitions to review (found by this run)

| Case | Ours | Baseline | Question to decide |
|---|---|---|---|
| canceled_orders | 461 | 625 | Count orders through items, or every row in `orders`? (164 canceled orders have no items) |
| reviews_2018 | 53,854 | 56,164 | A review's year: the order's purchase date, or the review's own date? |
| orders_by_status | 7 statuses | 8 statuses | Statuses of orders with no items are missing in ours |
| paid_by_payment_type | 4 types | 5 types | `not_defined` appears only outside delivered orders |

Decided in M2 step 3c, one case at a time; decisions go to §0.

## Interview one-liner

"On the same 34 questions, plain text-to-SQL with Haiku scored 5 / 34, and 21 / 34 with the
business rules in the prompt. Our semantic layer scored 34 / 34: rules applied in code are
followed every time, and questions that should stop are refused. The baseline also found
definitions worth reviewing."

## How to run again

From `backend/` (Docker running):

1. `uv run python -m adaa.evals.run` — our agent, when the cases changed (~$0.04).
2. `uv run python -m experiments.text_to_sql.run` — the baseline, A and B (~$0.015).
3. `uv run python -m experiments.text_to_sql.score` — scoring and the review file (free).

Then add a new "Results — run <date>" section above, and keep the old ones for comparison.
A stronger model (for example Sonnet) is added as a variant only if Haiku fails badly.
