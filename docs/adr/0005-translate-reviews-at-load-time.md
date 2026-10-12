# Portuguese reviews are translated once, at load time

Olist reviews are in Portuguese; the manager asks and reads in English. Translation is part of the ingestion pipeline: each review is translated to English once when loaded (including the daily refresh), both versions are stored, and search runs over the English. Nothing is translated while the manager waits, which protects the speed targets, and English text lets the builder read reviews to write and check tests. Quotes shown to the manager are marked "translated from Portuguese".

## Considered Options

- **Search Portuguese directly, translate only what's shown.** Multilingual search model, no upfront job, keeps original wording — but cross-language search is usually weaker on short slangy text, and translating on every answer adds time and cost at question time. Not chosen for the product; built as a measured comparison (retrieval quality, speed, cost on the same review questions) as a **nice-to-have, stretch** item — text-to-SQL is the core evidence-backed comparison.

## Consequences

- One-time translation job over all reviews with text (~40k, to be confirmed by profiling), plus incremental translation in the daily refresh.
- Translation can lose slang/nuance; the original is kept for checking.
- Open for design: translation tool (local model vs LLM API — cost/time trade-off).

## Questions that drove this

- Does this work happen once, or on every question? What does that do to latency and cost?
- Which option is easier to test and debug?
- What is lost in translation, and how do we keep a way back to the original?
