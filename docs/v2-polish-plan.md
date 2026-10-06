# V2 Polish Plan

**Status (2026-10-06):** Part A ✅ done · Part B: B1a/B1b/B1c/B2 ✅ done, B3 moved to after Part M · **Next: Part M (model audit)**. Open blocker: answer-generator model returns 404 (see Findings under Part B).
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
| M | M1–M5 model audit | 🔜 | Next. Settles the answer-generator model (planner/fixer/replanner frozen) |
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
- Only models that work with the user's Groq key are considered (today: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, plus others on the key's model list that fit the job).
- **Planner, param fixer and replanner stay unchanged.** They drive accuracy, and changing them would shift the frozen baseline. They are inventoried, priced and justified, but not swapped. Better alternatives are noted for V3.
- **Answer generator is the only component that may change.** It is just the final text-writing step, and its current model is unavailable.

| # | Change | Why |
|---|---|---|
| M1 | **Inventory:** a table of every LLM call in the system (planner, param fixer, replanner, answer generator, and the Part D code-gen baseline). For each: model, job, settings (temperature, reasoning effort, JSON mode), and tokens per call (from B1c) | Shows exactly where LLMs are used |
| M2 | **Availability and price check:** for each model, whether the key can use it, price per 1M input/output tokens, rate limits and context size, with the date checked | Prices and availability change; one model is already missing |
| M3 | **Answer-generator comparison:** on a small fixed pilot (about 10-12 queries), compare the available candidates for this job on answer correctness (using the B2 number check), cost and latency | Turns "I picked it" into "I measured it" |
| M4 | **Decision per job:** keep or change, with the reason. Planner, fixer and replanner: keep (frozen for the baseline). Answer generator: pick the best available candidate | Keeps the baseline stable while fixing what is broken |
| M5 | **Document it:** one "Model audit" table (job x model x why x price x result) in this file, copied into `docs/architecture.md`, and `docs/others/groq-model-details.md` refreshed. No new markdown files | Visible proof of the thinking |

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
