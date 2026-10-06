# V2 Polish Plan

**Status (2026-10-06):** Part A ✅ done · Part B: B1a/B1b/B1c/B2 ✅ done, B3 moved to after Part M · Part M: M1 ✅, M2 ✅, M3 skipped (decision), M4 ✅, **next M5 (document the audit)**. ⚠ Suspected (unconfirmed) free-tier limits on the key — user checking billing; it limits eval run speed. Open blocker: answer-generator model returns 404 (see Findings under Part B).
**Branch:** `version2`
**Outcome:** a clean, honest, measured, tagged `v2.0` release that serves as the frozen baseline for V3.

### Progress tracker (✅ done · 🔜 next · ⬜ not started · ⏸ deferred)

| Part | Item | Status | One-line summary |
|---|---|---|---|
| A | A1–A6 hygiene, tests, CI | ✅ | Eval tracked, docs fixed, 75 offline tests, CI + pinned requirements |
| B | B1a plan + critic check per step | ✅ | `critic_check`/`critic_reason` in trace; `plan`, `trace` in eval record |
| B | B1b fixer / replanner events | ✅ | `events` in state; real fix and replan counts |
| B | B1c tokens, cost, latency per LLM call | ✅ | `llm_calls` log; `cost_usd`; `eval/pricing.py` |
| B | B2 answer number check | ✅ | `eval/answer_check.py`; found Q31, Q34, Q41, Q43 hallucinations in saved runs |
| M | M1 inventory of LLM calls | ✅ | Table of every LLM job: model, settings, tokens (see Part M) |
| M | M2 availability, price, limits | ✅ | 5 usable models; missing ones were deprecated by Groq; limits suspiciously low (see finding) |
| M | M3 answer-model audition | ⏭ skipped | User decision: Groq-only, one model (`gpt-oss-20b`) for all jobs; no pilot needed |
| M | M4 switch answer model to `gpt-oss-20b` | ✅ | `ANSWER_MODEL` swapped, low reasoning effort, `max_tokens` 1024, empty answer = failure; 4/4 real answers LLM-written and pass B2 |
| M | M5 document the model audit | 🔜 | Next: audit table into `docs/architecture.md`, refresh `docs/others/groq-model-details.md` (README/CLAUDE.md/architecture lines already done) |
| B | B3 run each eval 3× | ⏸ | Moved: build and run after Part M, so the first counted run uses a working answer model |
| C | Failure-cause breakdown | ⬜ | Needs the B3 run |
| D | Baseline experiment | ⬜ | Code-gen baseline + ablation, reuses the B3 runner |
| E | Write-up (decisions, README, case study) | ⬜ | |
| F | Tag `v2.0` | ⬜ | Then `v2.1` simple answer-hallucination fix |

Each item, when completed, gets a dated entry in the **Completion log** at the bottom of this file.


---

## Context: why this plan exists

The goal is to raise ADAA to the standard expected of a **mid-level / lead AI engineer** portfolio
project, so that a reader quickly sees someone who can design, build, measure and explain a system
end-to-end.

The benchmark (from personal research on what makes a portfolio project stand out) says a project
reads as hire-worthy when it makes the builder's **judgment under failure** visible:

1. **An anticipated (not just patched) failure mode** — designed against in advance.
2. **Evaluation that separates failure types** — not one blended accuracy number.
3. **An explicit rejected alternative** — "we considered X and rejected it because Y", ideally with evidence.
4. **Contact with something messier than a curated demo** — messy data, ideally real users.

### Overall roadmap (two tracks, sequential)

| Track | Branch | What it does |
|---|---|---|
| **V2 Polish** (this doc) | `version2` | Work with what exists. Fix, document, instrument and measure. Tag `v2.0`. **No behaviour changes.** |
| **V3** — see [v3-problem-statement.md](v3-problem-statement.md) | new branch | Redefine the problem: real, messy, multi-table Olist e-commerce data in PostgreSQL, plus customer reviews (RAG), with routing, ambiguity handling and semantic guardrails. Same architecture, extended. (Superseded the earlier "normalized Superstore" idea — see V3 decision D1.) |

V3 is the **same project, next version**, not a separate project. The planner → constrained tools →
critic → fix/replan → answer architecture is independent of the data source. V2's measured
failures feed V3's design. The README tells one evolution story: V1 → V2 → V3.

### What the repo review found (state at start of this plan)

**Strong already:** LangGraph pipeline with typed `PipelineState`, real param fixer and replanner,
an 8-check rule-based critic, a 63-query eval in 4 categories with pandas ground truth, Langfuse
tracing, a live Streamlit demo, and honest "What Is Not Caught" / per-query failure analysis in
[failure-modes.md](failure-modes.md) and [evaluation.md](evaluation.md).

**Gaps:**
- **The eval can't be checked from GitHub.** `.gitignore` excludes `eval/`. The docs cite
  `test_cases2.py`, `test_cases3.py`, `multiturn_test_cases.py`, `run_multiturn_eval.py` and the
  June 2026 result files, none of which are tracked. Only the April results are committed.
- **The critic checks outputs, not plans.** `critique()` in `src/critics/rule_based_critic.py`
  checks the tool's output DataFrame after execution. Pydantic checks the plan before execution.
  Some descriptions imply pre-execution validation, which overclaims.
- **The critic rarely fires.** Avg retries 0.03 on single-turn (about 1 in 30 queries). Every
  observed failure was semantic (Q06 missing filter, answer-generator arithmetic, superset
  DataFrames, 4-turn context), which is exactly what the critic is documented not to catch.
- **Eval records can't support a failure-cause breakdown.** They store `retries` and
  `had_step_error` but not the plan, which critic check fired, or why a query failed.
- **No rejected alternative was measured.** The design-decisions table in
  [architecture.md](architecture.md) is short and has no evidence behind it. No simple baseline
  comparison was ever run.
- **Tests and CI:** only `tests/test_schema_gen.py`; no CI.
- **Hygiene:** `check_gt.py` and `eval_report_final.md` at the repo root, `notebooks/file1.ipynb`,
  untracked `PROJECT_GUIDE.md`, contradictions across docs (9 vs 10 tools, `llama-3.1-8b` vs
  `openai/gpt-oss-20b`), `git clone <repo-url>` placeholder in the README.

---

## Part A — Repo credibility and hygiene  ✅ DONE

**Status: ✅ done.** What was built and how it was verified: see the Completion log at the bottom.  
**Notes:** CLAUDE.md stays private (gitignored) but was updated. `docs/others/` kept public. Tests run with Python 3.13 (pandas 3 needs 3.11+).  

*Why: today a recruiter can't check the headline numbers, and the repo has loose ends.*

| # | Change | Why |
|---|---|---|
| A1 | Stop gitignoring `eval/`. Commit the eval code (`test_cases2.py`, `test_cases3.py`, `multiturn_test_cases.py`, `run_multiturn_eval.py`) and the June result files the docs cite | The 96.7% and 75% numbers currently point to files that aren't on GitHub |
| A2 | Remove or relocate stray files: `check_gt.py` → `dev_checks/`, `eval_report_final.md` → `docs/`, `notebooks/file1.ipynb` (delete or rename), and decide on `PROJECT_GUIDE.md` | Clean top level = a careful engineer |
| A3 | Fix contradictions: 9 vs 10 tools, model name mismatch, the `git clone <repo-url>` placeholder, V1 stubs still listed as stubs | Small inconsistencies cost trust |
| A4 | Add `.env.example`; pin versions in `requirements.txt` | Someone else can actually run it |
| A5 | **Unit tests that don't need an LLM:** each of the 10 tools, all 8 critic checks, the schema generator, and the graph routing with the LLM mocked | Deterministic tests show engineering discipline |
| A6 | **GitHub Actions CI** running those tests on every push, with a badge in the README | Visible proof the tests pass |

## Part B — Make the instrumentation honest

**Status:** B1a, B1b, B1c, B2 ✅ done (see Completion log). B3 ⏸ moved to after Part M.  
**Findings so far — ⚠ FINDING (2026-10-06), handled in Part M:** `llama-3.1-8b-instant` (the `ANSWER_MODEL`) returns 404 `model_not_found` for this Groq key; it is no longer in the account's model list. `answer_gen_node` silently falls back to a deterministic non-LLM answer, so new eval runs do NOT exercise the LLM answer generator and are not comparable to the June results. Caught by B1c instrumentation. Needs a decision before any full eval re-run.  
**Pilot cost data (4 real queries; planner only, since the answer call fails):** ~2,690 input / ~160 output tokens per query ≈ $0.00025/query.  
**B2 audit of saved results (free, 144 answers across all `eval_*.json`):** 104 pass, 6 flagged, 33 n/a (old `<think>` traces or non-answers), 1 no numbers. Flags: Q31 twice (answer total $2,316,900.86 / $1,317,000.92 vs real $2,297,200.86), Q34 ($630,215 vs real $733,215), Q41 ($763,819 unsupported), Q43 (4 invented ship-mode totals) — all genuine answer-generator hallucinations — plus one April answer truncated mid-number. **Known limit:** numbers only; it cannot catch mislabelled-but-present values (Q43's "region totals" are really the Standard Class rows) or wrong wording, and small integers can match derived values by chance.  
**Observed:** one transient no-plan failure on Q03 (passed on re-run) — the kind of infrastructure failure Part C should label.  

*Why: you can't explain failures you didn't record.*

| # | Change |
|---|---|
| B1 ✅ | The eval runner records, per query: the generated plan, **which critic check fired** at each step, param-fixer and replanner events, and tokens, cost and latency per LLM call |
| B2 ✅ | **Automatic hallucination check:** pull the numbers out of the answer text and check them against the result DataFrame. Catches Q41-style errors ($763K reported vs $286K actual) automatically instead of by hand |
| B3 ⏸ | Run each eval **3 times** and report the average and spread. Turns "Q06 was a fluke" from a guess into a measurement | **Moved to after Part M** (user decision 2026-10-06): the 3× run only counts once the answer-generator model is settled. Build the runner and run it then.

## Part M — Model audit (which model for which job, and why)

*Why: the choices of `gpt-oss-20b` and `llama-3.1-8b-instant` were never documented with evidence, and one of them is already gone from the API (see the FINDING under Part B). A reader should be able to see why each model was chosen, what it costs, and whether it was the best option.*

**Decisions (2026-10-06):**
- **Update:** the user chose to skip the M3 audition. V2 is Groq-only and one model, `openai/gpt-oss-20b`, serves all four LLM jobs (Groq's own recommended replacement for the deprecated answer model; cheapest Production-status option; `qwen3.8-27b` is Preview, `gpt-oss-120b` costs 2× with no measured benefit). The only risk (hidden reasoning tokens inside `max_tokens`) was handled in code and confirmed by a 4-query sanity run.
- Only models that work with the user's Groq key are considered (today: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, plus others on the key's model list that fit the job).
- **Planner, param fixer and replanner stay unchanged.** They drive accuracy, and changing them would shift the frozen baseline. They are inventoried, priced and justified, but not swapped. Better alternatives are noted for V3.
- **Answer generator is the only component that may change.** It is just the final text-writing step, and its current model is unavailable.

| # | Change | Why |
|---|---|---|
| M1 ✅ | **Inventory:** a table of every LLM call in the system (planner, param fixer, replanner, answer generator, and the Part D code-gen baseline). For each: model, job, settings (temperature, reasoning effort, JSON mode), and tokens per call (from B1c) | Shows exactly where LLMs are used |
| M2 ✅ | **Availability and price check:** for each model, whether the key can use it, price per 1M input/output tokens, rate limits and context size, with the date checked | Prices and availability change; one model is already missing |
| M3 ⏭ | **Answer-generator comparison (skipped by user decision, see Decisions below):** on a small fixed pilot (about 10-12 queries), compare the available candidates for this job on answer correctness (using the B2 number check), cost and latency | Turns "I picked it" into "I measured it" |
| M4 ✅ | **Decision per job:** keep or change, with the reason. Planner, fixer and replanner: keep (frozen for the baseline). Answer generator: pick the best available candidate | Keeps the baseline stable while fixing what is broken |
| M5 | **Document it:** one "Model audit" table (job x model x why x price x result) in this file, copied into `docs/architecture.md`, and `docs/others/groq-model-details.md` refreshed. No new markdown files | Visible proof of the thinking |

### M1 result — LLM call inventory (✅ 2026-10-06)

Source: `src/config.py`, the four LLM modules, `docs/others/groq-model-details.md`. Token figures marked *measured* come from real runs (B1c); *est.* are offline estimates from the prompt text (about 4 characters per token) and should be confirmed by a real run.

| Job | Model | Settings | Output format | Prompt size (input tokens) | Output tokens | Why this model (from the repo's notes) |
|---|---|---|---|---|---|---|
| **Planner** (question → JSON plan) | `openai/gpt-oss-20b` | temp 0.0, `reasoning_effort: low`, max 2048, timeout 90s, up to 2 attempts | `json_object`, validated afterwards by Pydantic | ~2,690 *measured* (system prompt ~1,900 + schema + question) | ~70–230 *measured* | Reasoning model that follows the strict tool/JSON rules; sits in the 20B size class with cheap pricing |
| **Param fixer** (repair a failed step) | `openai/gpt-oss-20b` | temp 0.0, `reasoning_effort: low`, max 2048, timeout 90s; one extra attempt if the fix is invalid | `json_object` → `ParamFixResponse` | ~1,100 *est.* (system ~450 + step/error/schema ~630) | small, ~100–300 *est.* | Same model as the planner, so one model family for all JSON jobs |
| **Replanner** (new plan after retries fail) | `openai/gpt-oss-20b` | temp 0.0, `reasoning_effort: low`, max 2048, timeout 90s; one extra attempt | `json_object` → `PlanResponse` | ~2,800 *est.* (system ~2,250 + failure context ~510) | like the planner, ~100–400 *est.* | Same as the planner (reuses its plan format) |
| **Answer generator** (result table → 2–3 sentence answer) | `llama-3.1-8b-instant` — **not available on this key (404)** | temp 0.3, max 256, timeout 90s | free text, no format enforced | ~230 *est.* for a small table (system ~180 + question + table; grows with table size) | ≤ 256 (cap) | Small non-reasoning model, chosen so `<think>` traces don't leak into the answer (config comment) |
| **Part D code-gen baseline** | not chosen yet | — | pandas code | — | — | Filled in when Part D is built |

**Observations:**
- Three of four jobs share one model (`gpt-oss-20b`). Only the answer generator uses a different one, and it is the one that is broken.
- Only the planner runs on every query. The fixer and replanner run only after a step fails (about 1 query in 30 historically), so they add very little cost.
- A typical query costs about 2,900 input + 400 output tokens across planner and answer generator, roughly $0.0003 (planner measured; answer call estimated).
- The answer generator reads the whole result table, so its input grows with table size; large tables are the main cost risk for that call.
- `gpt-oss-20b` is a reasoning model, so its output tokens include hidden reasoning. The measured output counts above already include it.

### M2 result — availability, price and limits (✅ 2026-10-06)

Method: one tiny real call per model (plain text and JSON mode) on the user's key, plus Groq's public models page. Limits are read from the response headers of those calls (`x-ratelimit-*`). Prices from `console.groq.com/docs/models`, checked 2026-10-06.

| Model | Works on this key? | Price per 1M tokens (in / out) | Context / max output | Limits seen on this key | Reasoning? | JSON mode | Verdict for the answer-generator job |
|---|---|---|---|---|---|---|---|
| `openai/gpt-oss-20b` | ✅ | $0.075 / $0.30 | 131,072 / 65,536 | 8,000 tokens/min, 1,000 requests/day (+200K tokens/day per 2026-06-20 notes) | Yes (hidden reasoning, no `<think>` in the text) | ✅ | **Candidate** — already used by 3 jobs, cheapest |
| `openai/gpt-oss-120b` | ✅ | $0.15 / $0.60 | 131,072 / 65,536 | 8,000 tokens/min, 1,000 requests/day | Yes | ✅ | **Candidate** — bigger, 2× price, likely overkill |
| `qwen/qwen3.8-27b` | ✅ | $0.80 / $4.00 | 131,072 / 16,384 | 8,000 tokens/min, 1,000 requests/day | No reasoning field, no `<think>` in the test | ✅ | **Candidate, but Preview status** (may be discontinued at short notice) — closest to the old "plain, non-reasoning" choice; ~10× the price |
| `allam-2-7b` | ✅ | not listed on the docs page | not listed | 6,000 tokens/min, 7,000 requests/day | No | ✅ | Weak candidate — Arabic-focused, price unknown |
| `openai/gpt-oss-safeguard-20b` | ✅ | $0.075 / $0.30 | 131,072 / 65,536 | 2,000 tokens/min | Yes | ✅ | Excluded — a safety-policy classifier, not a text writer |
| `llama-3.1-8b-instant` (current answer model) | ❌ 404 `model_not_found` (confirmed again) | — | — | — | — | — | Gone from this key |
| whisper-large-v3 (+turbo), orpheus (2), llama-prompt-guard-2 (2) | not tested | — | — | — | — | — | Excluded — speech / filter models, not text generators |

**Findings:**
1. **⚠ SUSPECTED (unconfirmed): the key's limits look like Groq's FREE tier, not the paid Developer plan.** This is an inference, not a confirmed fact; only the Groq console shows the real billing status (user is checking; the Developer role may have been disabled). Headers show 1,000 requests/day and 8,000 tokens/minute (the Developer plan lists 250K tokens/min and 1K requests/min), and the 2026-06-20 notes record hitting a 200K tokens/day cap. This contradicts the "paid plan" assumption behind open question 1. Billing status is only visible in the Groq console, so the user should check it.
   - *Impact:* the planner alone uses about 2,700 tokens per query, so 8,000 tokens/min is only about 2–3 queries a minute, and 200K tokens/day is only about 65 queries a day. B3 (63 queries × 3 runs) would take about 3 days; Part D (3 systems × 3 runs) about 9 days. Upgrading to the Developer plan removes this, and the whole project's token cost is under about $1.
2. **Reasoning-token risk for gpt-oss as answer writer:** these models spend hidden reasoning tokens inside `max_tokens`. The answer call caps output at 256, which could cut the answer short or leave it empty. M3 must test this (low reasoning effort and a higher cap would be needed if gpt-oss is chosen).
3. **Cost per answer call is negligible for every candidate** (about 230 input + 150 output tokens): gpt-oss-20b ≈ $0.00006, gpt-oss-120b ≈ $0.00013, qwen3.8-27b ≈ $0.0008. Price should not decide this; answer correctness (B2 check) and robustness should.
4. The model list on the key changed since `groq-model-details.md` was written (16 models then, 11 now). M5 refreshes that file.
5. **The missing models were deprecated by Groq, not hidden by tier.** Direct calls to `llama-3.3-70b-versatile`, `llama-4-scout`, `qwen3-32b`, `groq/compound(-mini)` and `kimi-k2` all return 404. Groq's deprecations page (checked 2026-10-06) lists `llama-3.1-8b-instant` as deprecated on 2026-08-16 with **`openai/gpt-oss-20b` as the recommended replacement**; `llama-3.3-70b-versatile` (2026-08-16), `llama-4-scout` and `qwen3-32b` (2026-07-17) and `groq/compound` (2026-09-21) are deprecated too. So the 11-model list is the current catalog, and Groq's own recommendation supports `gpt-oss-20b` as the answer-model candidate to beat in M3. (`kimi-k2` is not on the page I fetched; reason unknown.)

**Full Groq catalog cross-check (2026-10-06).** Sources: `console.groq.com/docs/models` (fetched twice, plus a web search), `/docs/deprecations`, and the live key. This is every model Groq lists, and whether the key can use it:

| Groq's status | Model | Price per 1M (in / out) | Context / max out | Docs rate limit (Developer plan) | On this key? | Usable as answer writer? |
|---|---|---|---|---|---|---|
| Production | `openai/gpt-oss-20b` | $0.075 / $0.30 | 131,072 / 65,536 | 250K TPM / 1K RPM | ✅ | ✅ candidate |
| Production | `openai/gpt-oss-120b` | $0.15 / $0.60 | 131,072 / 65,536 | 250K TPM / 1K RPM | ✅ | ✅ candidate |
| Production (Enterprise) | `llama-3.1-8b-instant` | Contact Sales | 131,072 / 131,072 | Contact Sales | ❌ 404 | ❌ (old answer model) |
| Production (Enterprise) | `llama-3.3-70b-versatile` | Contact Sales | 131,072 / 32,768 | Contact Sales | ❌ 404 | ❌ |
| Production | `whisper-large-v3`, `whisper-large-v3-turbo` | $0.111 / $0.04 per hour | audio | 200K / 400K ASH | ✅ listed | ❌ speech-to-text |
| Preview | `qwen/qwen3.8-27b` | $0.80 / $4.00 | 131,072 / 16,384 | 250K TPM / 1K RPM | ✅ | ⚠ candidate, but **Preview** (Groq: may be discontinued at short notice) |
| Preview | `openai/gpt-oss-safeguard-20b` | $0.075 / $0.30 | 131,072 / 65,536 | 150K TPM / 1K RPM | ✅ | ❌ safety classifier |
| Preview | `minimaxai/minimax-m2.7` | Contact Sales | 196,608 / 131,072 | Contact Sales | ❌ not on key | ❌ Enterprise only |
| Preview | `canopylabs/orpheus-v1-english`, `orpheus-arabic-saudi` | $22 / $40 per 1M chars | 4,000 | 50K TPM | ✅ listed | ❌ text-to-speech |
| Preview | `meta-llama/llama-prompt-guard-2-22m`, `-86m` | $0.03 / $0.04 | 512 | 30K TPM | ✅ listed | ❌ safety filters |
| not on Groq's page | `allam-2-7b` | not documented | not documented | not documented | ✅ (answers calls) | ❌ undocumented / legacy; not a safe pick |

**Conclusions from the cross-check:**
- Every non-enterprise model Groq lists is on the key, plus `allam-2-7b` (undocumented). Nothing usable is hidden from us by this key's tier.
- **Only two Production-status text models are usable: `gpt-oss-20b` and `gpt-oss-120b`.** `qwen3.8-27b` is Preview, so it could disappear and break a frozen baseline; treat it as a comparison point, not the pick, unless it is clearly better.
- Groq lists `llama-3.1-8b-instant` as Enterprise / Contact Sales on the models page and as deprecated (2026-08-16) on the deprecations page: either way it is not available to this key. (The docs pages also mention `qwen3.6-27b` while the key has `qwen3.8-27b`; the docs are slightly inconsistent.)
- The "Docs rate limit" column is the paid Developer plan. The key shows 8,000 tokens/min, far lower, so the key is not on that plan today (user checking billing/role).

**Cost gate:** the pilot is very cheap, but the estimate is shown and approved before it runs.
**Exit rule:** the answer-generator model must be settled here, before any full eval re-run (Part D). M3 depends on the B2 number check, so B2 comes first.

---

## Part C — Failure-cause breakdown

*Why: this is bar item 2, and the most direct hit on "evaluation separated by failure type".*

Classify every failure into a fixed set of categories. Proposed list:

| Category | Example from current eval |
|---|---|
| Planner: missing step (filter/sort) | Q06 aggregated everything instead of only Technology |
| Planner: superset result | Q36/Q37 returned all years or segments |
| Planner: wrong solvability call | Q33 refused a solvable query; Q41/Q43 attempted unsolvable ones |
| Structural (caught by critic) | Q23, fixed by the param fixer |
| Answer generator hallucination | Q41, Q43 |
| Context resolution (multi-turn) | The 4-turn MT failures |
| Infrastructure | API timeouts or errors |

**Output:** one table showing **category × count × responsible component × whether a guardrail
caught it**.

**Expected headline finding (to be confirmed by data):** almost all failures are about meaning,
not structure, and the structural critic catches very few of them. That's a measured fact that sets
up V3's semantic guardrails.

## Part D — Baseline experiment

*Why: this is bar item 3. It turns "I chose constrained tools" into "I measured it".*

Run the same 63 queries through:

| System | What it is |
|---|---|
| **ADAA V2** | The current pipeline |
| **Baseline 1: code generation** | One LLM call writes pandas code, run in a restricted sandbox (the common "chat with CSV" approach) |
| **Ablation: V2 without critic and fixer** | Shows how much the critic and repair loop actually contribute |

**Compare:** accuracy, failure categories, latency, tokens and cost, and safety (code execution
or not).

**Report the result honestly, whatever it is.** If code generation wins on accuracy, the story
becomes the trade-off ("slightly less accurate, but safe, checkable and debuggable"). Showing that
trade-off is a stronger signal than claiming a win.

## Part E — Write it up

| # | Change |
|---|---|
| E1 | **`docs/decisions.md`** in a decision-record style (*considered → rejected → because → evidence*): constrained tools vs code generation (with Part D numbers), rule-based vs LLM critic, LangGraph vs a plain loop, questions-only session memory, 3-turn window |
| E2 | **Correct the critic description everywhere.** It checks tool *outputs* after each step; Pydantic checks the *plan* before execution. Say exactly that |
| E3 | **README rewrite**, in this order: problem → headline result → failure breakdown → baseline comparison → design decisions → known limitations → architecture → setup. Add a demo screenshot or GIF |
| E4 | **Case-study write-up** (`docs/case-study.md`, optionally a blog post later): "What 63 queries taught me about where data agents actually fail" |

## Part F — Release

- Tag `v2.0` with release notes. This is the frozen baseline for V3.

---

## Order and effort

**A → B(1,2) → M → B3 → C → D → E → F** (B2 before M, since M3 uses the number check; B3 after M, since the 3× run needs a working answer model), roughly **2–3 weeks** part-time.

- Part D (baseline) is the largest single piece.
- Parts B and D both require several eval re-runs, so Groq rate limits will drive the schedule.

## Out of scope for V2 (deliberately)

- Fixing the observed failures (semantic checks, answer-generator arithmetic, 4-turn context).
  These are V3's job. Fixing them now would change the baseline.
- New data, new tables, new tools.

---

## Open questions (answer before approval)

1. **Eval re-runs:** ✅ **DECIDED:** Option A (full plan: 63 queries × 3 runs × 3 systems, ~570 runs). User is on a **paid Groq plan**. Runs happen *after* the instrumentation (Part B) and baseline (Part D) code is built. **Cost gate before any big run:** confirm the Groq model, input/output tokens per query, cost per query and total cost for one full pass (from a small pilot or Langfuse traces), then user approves.
   *(original question: OK with ~570 runs? Which Groq plan? Fallbacks were 2 runs or baseline on 30 single-turn queries only.)*
   **⚠ Update 2026-10-06 (M2):** the key's rate limits look like the FREE tier (8,000 tokens/min, 200K tokens/day), not paid; this is suspected, not confirmed. Either upgrade to the Developer plan (cheap, removes the bottleneck) or spread runs over days (B3 ~3 days, Part D ~9 days). User to check billing in the Groq console.
2. **Baseline sandbox:** ✅ **DECIDED:** restricted Python `exec` (whitelisted pandas/numpy only, no file/network/import access). Experiment-only on a public dataset run by us; write-up must note it is NOT safe for production (supports the constrained-tools argument).
   *(original question: restricted `exec` enough, or a proper sandbox?)*
3. **Failure labels:** ✅ **DECIDED:** auto-label from recorded data (API errors, critic fired, etc.); user reviews only the ambiguous ones.
   *(original question: auto-label + review ambiguous, or all manual?)*
4. **`PROJECT_GUIDE.md`:** ✅ **DECIDED:** it is a personal interview-prep guide. Keep local, add to `.gitignore` (not public). Reuse good parts in README / case study later.
   *(original question: keep, merge into docs, or ignore?)*
5. **`docs/others/`:** ✅ **DECIDED:** keep public as evidence of process. Add a short "design notes" index; mark finished to-do lists as done; fix stale content that contradicts the README.
   *(original question: keep public, or move out?)*
6. **Blog post:** ✅ **DECIDED:** later. V2 delivers only `docs/case-study.md`; a blog post can be derived from it after `v2.0` is tagged.
7. **Answer-generator hallucination:** ✅ **DECIDED:** capture and document it first (Part B2 auto number-check, Part C breakdown) and tag `v2.0` with the failure unfixed = frozen baseline. **After** the tag, try a simple fix as a separate step (`v2.1`); if it works, keep it and document before/after numbers. If no simple fix works, document that instead. Fix must stay small (no redesign). **Clarification (2026-10-06):** the forced model swap in Part M (the old model is gone from the API) is *not* this hallucination fix; it just restores a working answer step. The frozen `v2.0` baseline is V2 with a working answer model and the hallucination behaviour unfixed.
   *(original question: leave unfixed for V3, or fix in V2?)*



---

## Completion log

*One short entry per completed item: what was done, how it was verified, commit. Newest at the bottom. All commits are local on `version2` unless noted.*

**2026-10-06 — Part A ✅ (hygiene, tests, CI)**
- *Done:* `.gitignore` no longer hides `eval/` (eval code and April/June results now tracked; logs ignored); `PROJECT_GUIDE.md` ignored; `check_gt.py` → `dev_checks/`, `eval_report_final.md` → `docs/`, scratch notebook deleted; README/CLAUDE.md contradictions fixed (10 tools; planner/fixer/replanner = `gpt-oss-20b`, answer generator = `llama-3.1-8b-instant`), real clone URL, broken `docs/others/` links; `.env.example`, pinned `requirements.txt`, `requirements-dev.txt`; 75 offline tests (10 tools, 8 critic checks, param fixer, replanner, graph routing, mocked full-graph runs) with an autouse guard that blocks real Groq calls; GitHub Actions CI + README badge.
- *Verified by:* `dev_checks/check_part_a.py` (17/17), pytest with all API keys blanked.
- *Commits:* `0536910`, `4ce6513`, `978b619`, `4b5fdac`. *Note:* badge shows real status only after the first push.

**2026-10-06 — B1a ✅ plan + critic check per step**
- *Done:* `critic_check` and `critic_reason` added to each trace record (`src/core/executor.py`); eval records keep the full `plan` and `trace`. Instrumentation only.
- *Verified by:* `tests/test_trace_record.py`, `dev_checks/check_trace_fields.py` (3 real queries). Commit `6894b1e`.

**2026-10-06 — B1b ✅ param-fixer / replanner events**
- *Done:* `events` list in `PipelineState`; param fixer records old/new parameters, triggering error and critic check, and `changed`; replanner records old plan, new plan and result (the replanner overwrites the plan, so the old one was previously lost). Eval records get `param_fix_count`, `param_fix_effective_count`, `replan_count`.
- *Verified by:* `tests/test_events.py` (real nodes, faked LLM), `dev_checks/check_events.py`. Commit `fc8226d`.

**2026-10-06 — B1c ✅ tokens, cost, latency per LLM call**
- *Done:* `llm_generation` (`src/utils/langfuse_helper.py`) logs every LLM attempt, including failures, per run; pipeline returns `llm_calls`; eval records get token, latency and `cost_usd` totals; `eval/pricing.py` (gpt-oss-20b $0.075 in / $0.30 out per 1M tokens, verified on Groq's docs page 2026-10-06; llama price unverified).
- *Verified by:* `tests/test_llm_calls.py`, `dev_checks/check_llm_calls.py` (4 real queries). Commit `e981eaa`.
- *Found:* `llama-3.1-8b-instant` returns 404 for this key, so the answer step silently uses the non-LLM fallback (see Findings, Part B).

**2026-10-06 — Plan change: Part M (model audit) added.** Planner/fixer/replanner frozen; only the answer generator may change; candidates limited to models the key can use. Commit `557cf6c`.

**2026-10-06 — B2 ✅ answer number check**
- *Done:* `eval/answer_check.py` classifies each number in an answer as supported / derived / excused / unsupported; eval records get `answer_check`, `answer_numbers_unsupported`, `answer_is_fallback`.
- *Verified by:* `tests/test_answer_check.py`, `dev_checks/check_answer_check.py` (run over all 144 saved answers: 104 pass, 6 flagged, 33 n/a, 1 no numbers; the flags are real hallucinations Q31 ×2, Q34, Q41, Q43, plus one truncated answer). Commit `7215761`.

**2026-10-06 — Plan change: B3 moved to after Part M** (the full 3× run needs a working answer model).

**2026-10-06 — M1 ✅ LLM call inventory**
- *Done:* table of all LLM jobs (planner, param fixer, replanner, answer generator, Part D baseline placeholder) with model, settings, output format, prompt and output token sizes and the repo's stated reason for each choice, plus observations (3 of 4 jobs share `gpt-oss-20b`; only the planner runs on every query; answer generator input grows with table size). Documentation only, no code changes.
- *Verified by:* read from config and source; planner tokens are measured (B1c pilot), the other token figures are offline estimates and are marked as such. Commit: see git log.

**2026-10-06 — M2 ✅ model availability, price and limits**
- *Done:* tested every text-capable model on the key with real tiny calls (text and JSON mode), read rate limits from response headers, took prices and context sizes from Groq's models page. Result table and findings in Part M. Answer-generator candidates: `gpt-oss-20b`, `gpt-oss-120b`, `qwen3.8-27b` (weak: `allam-2-7b`); `gpt-oss-safeguard-20b` excluded.
- *Key findings:* (1) the key's limits look like Groq's free tier (suspected, unconfirmed; user checking billing), which would constrain B3 and Part D run time (open question 1 updated); (2) the missing models (incl. the old answer model) were deprecated by Groq on known dates, and Groq recommends `gpt-oss-20b` as the replacement. Also a reasoning-token truncation risk for gpt-oss as the answer writer (to test in M3).
- *Verified by:* about 12 real API calls (total cost well under $0.001). No code changes. Probe scripts were scratch files, not committed.

**2026-10-06 — M2 follow-up ✅ full Groq catalog cross-check**
- *Done:* compared Groq's full model list (models page fetched twice, web search, deprecations page) with the key's list and direct calls. Full table added to Part M. Only `gpt-oss-20b` and `gpt-oss-120b` are Production-status text models usable on the key; `qwen3.8-27b` is Preview (discontinuation risk); `allam-2-7b` is undocumented.
- *Verified by:* three independent sources agree on the catalog; a web fetch of the docs is a summary and could miss rows, so the key's own model list was used as the second check.

**2026-10-06 — M3 skipped, M4 ✅ answer generator moved to `gpt-oss-20b`**
- *Done:* `ANSWER_MODEL` → `openai/gpt-oss-20b` (`src/config.py`); answer call now `reasoning_effort: low`, `max_tokens` 1,024 (was 256, which hidden reasoning tokens could exhaust); an empty answer is now an error that falls back visibly (`answer_is_fallback`) instead of a blank success (`src/core/answer_generator.py`). README, CLAUDE.md (private) and `docs/architecture.md` updated with the one-model rationale. M3 audition skipped by user decision.
- *Behaviour change (the only one in V2 polish):* forced, because the old model is gone from the API. The 96.7% / 75% figures came from the llama answer writer; `v2.0` answers are written by `gpt-oss-20b`. State this in the write-up.
- *Verified by:* `tests/test_answer_generator.py` (121 offline tests pass); `dev_checks/check_answer_generator.py` on 4 real queries (Q01, Q11, Q20, Q29): all answers LLM-written (about 280 input / 75 output tokens, about 0.5 s), all pass the B2 number check, about $0.0003 per query end to end. Note: gpt-oss writes a narrow no-break space (U+202F) in some names ("New York"), harmless but relevant for text comparisons.

