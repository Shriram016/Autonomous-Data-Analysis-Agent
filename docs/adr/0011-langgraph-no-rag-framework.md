# The agent loop is built with LangGraph (state in PostgreSQL); no RAG framework

LangGraph runs the bounded loop, with its saved state (checkpoints) stored in our PostgreSQL. Three locked needs map onto features it already has: pausing for human approval and resuming (interrupts), surviving restarts (any worker can resume any job from the saved state), and step limits. Hand-building these is where bugs hide and does not make the project stand out. Review search uses no RAG framework: reviews are short rows already in PostgreSQL, and hybrid search is plain SQL over full-text search + pgvector.

## Considered Options

Researched 2026-10-11 across three layers (orchestration, retrieval, prompt optimisation).

- **Pydantic AI.** Typed, clean tool definitions, now with durable execution; less proven at scale for pause/resume. Runner-up.
- **OpenAI Agents SDK / Google ADK / Microsoft Agent Framework.** Lean towards one vendor or cloud, conflicting with the vendor-free LLM interface (ADR 0009).
- **CrewAI.** Built for multi-agent "teams"; weak pause/resume; we don't want multi-agent.
- **Plain Python loop.** Full control, but pause, saved state and resume all hand-built.
- **RAG frameworks (LlamaIndex, Haystack).** Strong for long-document loading/chunking/indexing, which we don't have; would add a layer over one SQL query. Data preparation matters more than the framework.
- **DSPy (prompt optimisation).** Not needed now; possible later for prompt tuning.

## Consequences

- One extra library family (LangGraph); V2 experience carries over.
- Checkpointer moves from V2's SQLite file to PostgreSQL: no extra database, shared by all workers.
- LLM calls inside graph nodes still go through `llm.complete(job, ...)` (ADR 0009), not LangChain model classes.

## Questions that drove this

- Which needs (pause, resume, step limits, saved state) must the framework cover, and which frameworks cover them well?
- Does the framework tie us to a vendor or cloud?
- Does our retrieval problem actually need a RAG framework, or is it one query?
- Are we stacking frameworks without a reason?
