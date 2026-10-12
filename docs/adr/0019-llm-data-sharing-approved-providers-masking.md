# Only approved LLM providers; send the minimum; mask personal and confidential data in code

Every LLM call sends company data to a third party, so:

1. **Approved providers only.** A provider (fallbacks included) is allowed only if its API terms say it does not train on our data; retention terms are recorded. The approved list lives in the model config. Free tiers that train on data are excluded.
2. **Send the minimum.** Thanks to the semantic layer, the LLM sees definitions and summarised results, not raw customer rows.
3. **Mask in code, at one door.** A masking function inside `llm.complete(...)` (ADR 0009) removes or replaces personal and confidential values before any call leaves; no code path can bypass it. The same function cleans prompts stored in logs and traces.
4. **What counts as personal / confidential is defined in a versioned config file** (e.g. customer IDs, zip prefixes, identifying combinations), reviewed like the semantic layer.

Control in our own code is stronger than relying on a provider's promises.

## Considered Options

- **No rules.** Simplest; a real company would block it. Rejected.
- **Self-hosted open models only.** Nothing leaves, but GPU cost, weaker models and slower answers would likely break the speed and cost targets. Documented as the option for strict environments; rejected here.

## Consequences

- Fewer free-tier options; model choice must check provider terms.
- Masking must not break answers: masked placeholders are mapped back in code where the manager is allowed to see the value.
- Eval/safety tests check that no listed value appears in outgoing prompts or traces.

## Questions that drove this

- Will the provider train on or keep our data, and for how long?
- What does the LLM actually need to see, and what are we sending that it doesn't?
- Where is the single point that every outgoing call passes through?
- Who defines what is personal or confidential, and where is that written down?
