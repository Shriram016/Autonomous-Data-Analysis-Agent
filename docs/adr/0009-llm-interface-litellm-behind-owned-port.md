# LLMs are called through one owned interface, with official SDKs in two adapters

> **Amended 2026-10-20 (M1.2):** LiteLLM removed. The original decision put LiteLLM behind the interface. We now use the providers' official SDKs in two hand-written adapters. The file name keeps its old slug so links still work.

All code calls one function we own, `llm.complete(job, ...)` (job = router, agent, answer, …). Behind it sit two adapters: **`anthropic`** (official Anthropic SDK, for Claude) and **`openai_compatible`** (official OpenAI SDK with a `base_url`, for OpenAI, Groq, DeepInfra, Together, Fireworks, Mistral, Gemini's OpenAI endpoint). The adapter, model, `base_url`, API-key variable name, thinking effort and price for each job, and its fallback chain, live in config and are chosen by eval results. A provider change inside those two API styles is a config change; a new API style is one new adapter file. Nothing outside `llm/` knows which provider runs. This satisfies the "switch to a backup provider, never a made-up answer" requirement, and keeps vendor code in one place (ports and adapters).

## Considered Options

- **Call one vendor directly (V2).** Simplest, but no fallback and vendor calls scattered across files; V2's direct `Groq(...)` calls in 4 modules hid a deprecated-model failure. Rejected.
- **LiteLLM behind the interface (the original choice).** One API for 100+ providers, built-in retry, fallback and cost table. Rejected on 2026-10-20: (1) we build retry, fallback, breaker and rate limiter ourselves inside `llm.complete` (§0 failure handling), so its main value overlaps our own work; (2) we need two API styles, not 100 providers; (3) supply-chain risk — on 2026-03-24 two malicious LiteLLM releases on PyPI stole credentials and `.env` secrets; (4) a large dependency with many open bugs, and new provider features (adaptive thinking, strict JSON) arrive later than in the official SDKs. Still possible later as one more adapter.
- **LiteLLM called directly from pipeline code.** Ties every module to the library. Rejected.
- **any-llm (Mozilla), PydanticAI, Instructor, gateways (Portkey, Bifrost, LiteLLM Proxy).** any-llm: cleaner (wraps official SDKs) but young. PydanticAI: an agent framework that overlaps LangGraph (ADR 0011). Instructor: strict JSON is now native in the providers. Gateways: a separate server to run — too much for now; revisit at deployment.

## Consequences

- Vendor SDK imports only inside the two adapter files.
- We keep a price per model in config (one line each) instead of a library cost table.
- Per-job model config enables model tiering (cheap model for simple steps) against the cost baseline.
- Behaviour differs between models even when the API matches, so the eval suite is the safety net for any model swap.
- The central rate-limit enforcement, retry, fallback and breaker live behind the same interface, written by us.
- **Structured output on every call (added 2026-10-13).** Each job declares a Pydantic output schema; `llm.complete` uses the provider's strict JSON-schema mode where supported, validates, retries once with the error, then falls back. No free-text parsing anywhere; prose is a field in the schema. Models without reliable schema support can't be used for a job.

## Questions that drove this

- What happens to the code when a provider is down, deprecates a model, or changes price?
- How many places must change to swap a model?
- Should we be tied to a vendor, a library, or only our own interface?
- Does a library earn its place if we build its main features ourselves? (2026-10-20)
