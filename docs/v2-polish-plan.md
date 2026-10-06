# V2 Polish Plan

**Status:** All 7 open questions answered. **Part A done** (A1–A6, verified by `dev_checks/check_part_a.py`). Next: Part B (plan first).
**Branch:** `version2`
**Outcome:** a clean, honest, measured, tagged `v2.0` release that serves as the frozen baseline for V3.

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

**Progress:** A1 ✅ (eval tracked, `.log` files ignored) · A2 ✅ (`check_gt.py`→`dev_checks/`, report→`docs/`, notebook deleted, `PROJECT_GUIDE.md` ignored) · A3 ✅ (10 tools; planner/fixer/replanner = `gpt-oss-20b`, answer gen = `llama-3.1-8b-instant`; README clone URL; broken `docs/others/` links) · A4 ✅ (`.env.example`, pinned `requirements.txt`, `requirements-dev.txt`) · A5 ✅ (75 offline tests: 10 tools, 8 critic checks, param fixer, replanner, graph routing + full mocked graph runs; autouse guard blocks real Groq calls) · A6 ✅ (`.github/workflows/ci.yml` + README badge; badge turns green after the first push).  
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

**Progress (B1 split into pieces, one approved at a time):** B1a ✅ plan + critic check/reason saved per step (`critic_check`, `critic_reason` added to the trace record in `executor.py`; `plan` and `trace` added to the eval record; verified by `tests/test_trace_record.py` and `dev_checks/check_trace_fields.py`) · B1b ✅ `events` list in `PipelineState` (param_fix: old/new params, `changed`, triggering critic check; replan: old plan, new plan, result) + `param_fix_count`, `param_fix_effective_count`, `replan_count` in eval records (`tests/test_events.py`, `dev_checks/check_events.py`) · B1c ✅ every LLM attempt (incl. failed) logged in `llm_generation` → `llm_calls` in pipeline result; eval record gets tokens, latency, `cost_usd`; `eval/pricing.py` (gpt-oss-20b $0.075/$0.30 per 1M verified 2026-10-06; llama price unverified) (`tests/test_llm_calls.py`, `dev_checks/check_llm_calls.py`) · B2 ⬜ · B3 ⬜  
**⚠ FINDING (2026-10-06) — OPEN DECISION:** `llama-3.1-8b-instant` (the `ANSWER_MODEL`) returns 404 `model_not_found` for this Groq key; it is no longer in the account's model list. `answer_gen_node` silently falls back to a deterministic non-LLM answer, so new eval runs do NOT exercise the LLM answer generator and are not comparable to the June results. Caught by B1c instrumentation. Needs a decision before any full eval re-run.  
**Pilot cost data (4 real queries, planner only works):** ~2,690 input / ~160 output tokens per query for the planner ≈ $0.00025/query.  
**Observed:** one transient no-plan failure on Q03 (passed on re-run) — the kind of infrastructure failure Part C should label.  

*Why: you can't explain failures you didn't record.*

| # | Change |
|---|---|
| B1 | The eval runner records, per query: the generated plan, **which critic check fired** at each step, param-fixer and replanner events, and tokens, cost and latency per LLM call |
| B2 | **Automatic hallucination check:** pull the numbers out of the answer text and check them against the result DataFrame. Catches Q41-style errors ($763K reported vs $286K actual) automatically instead of by hand |
| B3 | Run each eval **3 times** and report the average and spread. Turns "Q06 was a fluke" from a guess into a measurement |

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

**A → B → C → D → E → F**, roughly **2–3 weeks** part-time.

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
7. **Answer-generator hallucination:** ✅ **DECIDED:** capture and document it first (Part B2 auto number-check, Part C breakdown) and tag `v2.0` with the failure unfixed = frozen baseline. **After** the tag, try a simple fix as a separate step (`v2.1`); if it works, keep it and document before/after numbers. If no simple fix works, document that instead. Fix must stay small (no redesign).
   *(original question: leave unfixed for V3, or fix in V2?)*
