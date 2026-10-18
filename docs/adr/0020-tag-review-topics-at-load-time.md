# Tag review topics once at load time, so "how often" becomes a counted number

During ingestion, after translation, the LLM labels each review that has text with one or more topics from a fixed list (e.g. late delivery, damaged item, wrong item, product quality, seller communication, other). The list lives in a versioned config file, reviewed like the semantic layer. Tags are stored in the business schema and exposed as a semantic-layer dimension ("review topic").

At question time, "what do customers complain about most?" is answered by **counting tags** (exact, via the semantic layer), while review search supplies the **quotes**. Search alone can only show what people say, not how often.

## Considered Options

- **Search only (top ~30 reviews).** Simplest, but the answer must avoid frequency claims ("most", "common"); managers ask exactly those. Rejected.
- **Count at question time** (LLM reads hundreds of reviews per question). Slow and expensive; breaks the speed and cost targets. Rejected.

## Consequences

- One more LLM step in ingestion (~40k reviews with text once, then only new ones daily); cost is one-time, like translation (ADR 0005).
- Tag quality needs its own check: a small hand-labelled sample measures tagging accuracy.
- Changing the topic list means re-tagging; the list version is recorded with each answer, like the semantic-layer version.
- Hybrid questions get easier: "late-delivery complaints by state" is a plain numbers query.
- Topics outside the list fall into "other"; search still finds them, but they aren't counted separately.

## Questions that drove this

- Does the manager's question claim frequency ("most", "often"), and can a top-N search support that?
- Can we afford to read many reviews per question within the speed and cost targets?
- What's done once at load time vs on every question?
