# Design Decisions

Each entry says what we chose, what we considered, why, and the evidence. Where we have no measurement, we say so. Full evidence: [v2-polish-plan.md](v2-polish-plan.md).

## 1. Fixed tools instead of LLM-written code
- **Chose:** the LLM writes a plan and 10 tested tools compute.
- **Considered:** letting the LLM write pandas code, run in a sandbox.
- **Why:** nothing but our tools can run, every step is visible and checked, and the system can refuse what it can't do.
- **Evidence:** same model, 63 questions, one run each: **49 vs 49 correct**. The code version was about 3.5× cheaper ($0.00013 vs $0.00046 per question) and faster, but it gave silent wrong answers (outdated pandas syntax), crashed once, lost context, and its blocklist once blocked a legitimate `df.query()`. In a 5-question hostile test both systems stayed safe.
- **Trade-off:** on this data ADAA is not more accurate and costs more. We accept that for safety and traceability.

## 2. A rule-based critic, not an LLM critic
- **Chose:** 8 deterministic checks on each tool's output.
- **Considered:** an LLM that judges each step.
- **Why:** deterministic, free and fast.
- **Evidence:** it caught **0 of the 15 failures**, because they are about meaning and it checks structure. An LLM critic was never tested, so this is an open question for V3.

## 3. One model (`gpt-oss-20b`) for every LLM job
- **Chose:** `gpt-oss-20b` on Groq for the planner, param fixer, replanner and answer generator.
- **Considered:** `llama-3.1-8b-instant` (the original answer model), `gpt-oss-120b`, `qwen3.8-27b`.
- **Why:** the original was deprecated and returned errors. `gpt-oss-120b` costs twice as much and was not tested. `qwen3.8-27b` is Preview and can be discontinued.
- **Evidence:** about $0.0005 per question, and 4 of 4 sanity answers passed the number check.
- **Risk:** one model is a single point of failure, with no fallback.

## 4. LangGraph instead of a plain loop
- **Chose:** LangGraph with typed state and conditional routing.
- **Considered:** V1's hand-written Python loops.
- **Why:** retries, replanning and step routing become explicit and traceable.
- **Evidence:** a design choice only. We did not measure it against the old loop.

## 5. Session memory: the last 3 questions only
- **Chose:** keep the last 3 questions of a session, not answers or tables.
- **Considered:** a longer window, or storing results.
- **Why:** simple, with no stale results or large state.
- **Evidence:** multi-turn got 10 of 16 (4-turn follow-ups 1 of 4). The two 4-turn failures we reviewed (MT13, MT15) happened with the earlier turns still in memory, so window size was not the cause. A longer window was not tested.

## 6. One table per answer
- **Chose:** every answer is a single table, so compound questions are refused.
- **Considered:** multi-table answers.
- **Why:** keeps the tools and the checks simple.
- **Evidence:** ADAA refused 5 of 10 compound questions. The code version answered many usefully (for example total sales and profit in one table), so this choice limits what ADAA can do.
