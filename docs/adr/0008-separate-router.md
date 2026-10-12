# A separate router classifies each question before the agent loop

After follow-ups are rewritten into standalone questions, a router classifies each question into one route (numbers, reviews, hybrid, clarify, refuse, off-topic, metadata). Clarify/refuse/off-topic/metadata exit early, before any loop or database work, meeting their < 2s target; the bounded loop starts with only the chosen route's tools, which cuts planning mistakes (V2 showed planner errors dominate); and routing accuracy (S3) is measurable on its own.

## Considered Options

- **Loop decides itself.** One fewer step, but routing is hidden inside the loop and hard to measure, the prompt is larger, and clarify/refuse happen only after the loop starts. Rejected as the product; a router-vs-no-router comparison is a low-priority stretch item.
- **Keyword rules.** Instant and free, but brittle. Rejected.

## Consequences

- One extra step per question (cost and latency counted per route).
- A misroute is a distinct failure cause in the eval.
- Open for design: how the router classifies (LLM call with structured output, small classifier model, embedding-based), chosen by measured accuracy, latency and cost; low router confidence may trigger clarify.

## Questions that drove this

- Which question types must be fast, and can they exit before expensive work?
- Does a smaller toolset reduce agent mistakes?
- Can we measure this decision on its own?
