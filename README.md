# Autonomous Data Analysis Agent (ADAA)

A deterministic AI pipeline that converts natural language questions into verified, computed answers — no free-form code generation, every step planned, executed, and validated.

**Live demo:** [autonomous-data-analysis-agent-s16.streamlit.app](https://autonomous-data-analysis-agent-s16.streamlit.app/)

---

## What It Does

- Takes a natural language question about a dataset (e.g. "Which are the top 5 states by total sales?")
- Generates a structured execution plan using an LLM, runs it through predefined tools, and validates every step with a rule-based critic
- Returns the computed answer as both a DataFrame and a plain English summary, with a full reasoning trace
- Supports multi-turn follow-ups — stores the last 3 questions per session so queries like "What about 2015?" resolve context from prior turns

---

## Architecture

```
User Query
    ↓
Schema Generator          → Dataset → concise JSON schema (never the raw df)
    ↓
Planner (LLM)             → Query + schema → JSON execution plan
    ↓
┌─────────────────────────────────────────────────────┐
│  LangGraph Execution Loop                           │
│  ┌───────────────────────────────────────────────┐  │
│  │ Executor                                      │  │
│  │     ↓                                         │  │
│  │ Tool Layer (10 predefined tools)              │  │
│  │     ↓                                         │  │
│  │ Rule-Based Critic (8 deterministic checks)    │  │
│  │     ↓                                         │  │
│  │ pass → next step     fail → Param Fixer (LLM) │  │
│  │                      fail → Replanner (LLM)   │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
    ↓
Answer Generator (LLM)   → DataFrame → plain English answer
    ↓
Final Answer + Reasoning Trace
```

---

## Eval Results

Tested across **63 queries** in 4 categories on the Sample Superstore dataset:

| Category | What it tests | Cases | Result |
|---|---|---|---|
| **Single-Turn** | Core pipeline accuracy — aggregation, filtering, grouping, ranking, time-based, multi-condition, derived calculations | 30 | **29/30 passed (96.7%)** |
| **Pseudo-Compound** | Queries that look compound but are solvable in a single plan | 7 | **4 correct, 2 partial, 1 failed** |
| **Truly Compound** | Queries requiring two separate plans — expected unsolvable | 10 | **6 correctly unsolvable, 2 hallucinated, 2 misclassified** |
| **Multi-Turn** | Follow-up questions relying on context from prior turns | 16 | **12/16 passed (75%)** |

> Full analysis: [docs/evaluation.md](docs/evaluation.md)

---

## Key Features

- **LangGraph orchestration** — The pipeline is built on LangGraph with structured state management, conditional edges, and retry/replan logic implemented as graph nodes.
- **Predefined tool layer** — The LLM selects from 10 predefined tools and specifies parameters. No free-form code is ever generated.
- **Rule-based critic** — Every tool call is validated by 8 deterministic checks. Failures route to an LLM-powered param fixer or replanner for self-correction.
- **Session memory** — A sliding window of the last 3 questions per session enables multi-turn follow-up queries.
- **Langfuse observability** — Every LLM call is traced with prompt, response, token usage, and latency.
- **Conversation UI** — A Streamlit chat interface with history display and session management.
- **Eval pipeline** — 63 test cases across 4 categories, each with pandas ground truth and automated comparison.

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python |
| Data operations | Pandas |
| LLM | Groq API — `openai/gpt-oss-20b` |
| Orchestration | LangGraph |
| Data validation | Pydantic |
| Observability | Langfuse |
| UI | Streamlit |

---

## Getting Started

**Prerequisites:** Python 3.9+, a [Groq API key](https://console.groq.com/), a [Langfuse account](https://langfuse.com/) (optional, for observability)

```bash
# 1. Clone the repository
git clone <repo-url>
cd adaa

# 2. Create a virtual environment and install dependencies
python -m venv agent_env
agent_env\Scripts\activate
pip install -r requirements.txt

# 3. Set up your API keys
echo "GROQ_API_KEY=your_key_here" > .env
echo "LANGFUSE_PUBLIC_KEY=your_key_here" >> .env
echo "LANGFUSE_SECRET_KEY=your_key_here" >> .env

# 4. Launch the Streamlit UI
streamlit run app.py

# 5. (Optional) Run the evaluation pipeline
python eval/run_eval.py --round 1
python eval/run_multiturn_eval.py
```

---

## Documentation

- [Architecture](docs/architecture.md) — Pipeline flow, components, state management, design decisions
- [Tools](docs/tools.md) — All 10 tools with parameters, examples, and ordering constraints
- [Evaluation Report](docs/evaluation.md) — Full eval results across 4 categories with failure analysis
- [Failure Modes](docs/failure-modes.md) — Handled failures, known limitations, retry flow
- [V2 Plan](docs/v2-plan.md) — Upgrade scope and status: LangGraph, session memory, Langfuse, eval pipeline

---

## V1 → V2 Evolution

V1 was built from scratch with raw Python orchestration — manual loop control, dict-based state, and stub implementations for error recovery. It validated the core idea: an LLM plans, predefined tools execute, a rule-based critic validates.

V2 addressed the gaps that V1 exposed:

| What changed | V1 | V2 |
|---|---|---|
| Orchestration | Manual Python loops | LangGraph with conditional edges |
| State management | Raw dicts passed between functions | Structured `PipelineState` TypedDict |
| Error recovery | Param Fixer and Replanner were stubs | Real LLM-powered nodes that correct parameters and generate new plans |
| Session memory | None — each query was independent | Sliding window of last 3 questions enables multi-turn follow-ups |
| Observability | File logging only | Langfuse tracing on every LLM call (prompt, response, tokens, latency) |
| UI | Single-turn form with one result displayed | Conversation-style chat with history |
| Evaluation | 30 single-turn queries | 63 queries across 4 categories (single-turn, pseudo-compound, compound, multi-turn) |
