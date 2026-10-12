# Short-term memory keeps compact turns and references, not full history

Within a conversation, the agent keeps the last ~5 turns, each as: the question, the structured request used, and a one-line answer summary. Large query results are stored separately and referenced by ID, never pasted into prompts or the saved state. Keeping the structured request makes follow-ups precise ("What about Rio?" = last request with a new state filter) instead of guessing from chat text; references keep prompts, cost and checkpoint size small. A summary of older turns is added only if tests show a need.

## Considered Options

- **Full history in every prompt.** Never forgets, but grows without limit; slow and costly. Rejected.
- **Last few questions only (V2: last 3).** Small, but loses what was computed, so follow-ups are resolved by guesswork. Rejected.

## Consequences

- Turn records and stored results need retention limits (how long, how big).
- Follow-up rewriting reads structured requests, so the request format is part of the memory contract.
- Long-term memory (across conversations) is a separate decision.

## Questions that drove this

- What does a follow-up actually need from earlier turns: the words, or what was computed?
- What grows without limit as a conversation gets long, and where does it end up (prompt, saved state)?
- What is the cheapest design that resolves follow-ups precisely?
