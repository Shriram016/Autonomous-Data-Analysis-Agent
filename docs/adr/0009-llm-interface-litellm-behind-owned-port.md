# LLMs are called through one owned interface, with LiteLLM behind it

All code calls one function we own, `llm.complete(job, ...)` (job = router, agent, answer, …). Behind it, LiteLLM speaks to many providers and supplies fallback and cost counting. The model for each job, and its fallback chain, live in config and are chosen by eval results. This satisfies the "switch to a backup provider, never a made-up answer" requirement, and keeps vendor code in one place (ports and adapters). If LiteLLM becomes a problem, only the adapter file changes.

## Considered Options

- **Call one vendor directly (V2).** Simplest, but no fallback and vendor calls scattered across files; V2's direct `Groq(...)` calls in 4 modules hid a deprecated-model failure. Rejected.
- **Own interface with hand-written adapters per vendor.** Full control, but we'd rebuild what LiteLLM already does. Rejected as the starting point (still possible behind the same interface).
- **LiteLLM called directly from pipeline code.** No adapters to write, but ties every module to the library. Rejected.

## Consequences

- Vendor SDK / LiteLLM imports only inside the adapter.
- Per-job model config enables model tiering (cheap model for simple steps) against the cost baseline.
- Behaviour differs between models even when the API matches, so the eval suite is the safety net for any model swap.
- The central rate-limit enforcement can live behind the same interface.

## Questions that drove this

- What happens to the code when a provider is down, deprecates a model, or changes price?
- How many places must change to swap a model?
- Should we be tied to a vendor, a library, or only our own interface?
