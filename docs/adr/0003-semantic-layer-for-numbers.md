# Numbers are computed through a semantic layer, not LLM-written SQL

Metrics (e.g. revenue, late-delivery rate), dimensions (e.g. state, category, month), table joins and messy-data rules are defined once by us. The LLM only fills a structured request (metric, breakdown, filters, period, sort/limit); code validates it and compiles it to SQL. The manager cannot verify a number, so a silently wrong number is the worst failure, and the parts most likely to go silently wrong (joins, cancelled orders, missing dates) are fixed by us, not guessed by the model. Text-to-SQL is built as the measured comparison baseline.

## Considered Options

- **LLM writes SQL (text-to-SQL).** Answers almost anything, but can silently pick wrong joins or filters. Rejected as the product; **kept as the core baseline**: both run on the same questions and are compared on accuracy, coverage, failure types, cost and latency.
- **Fixed function per question (V2 style).** Very safe, but needs hundreds of tools to cover a 9-table dataset.

## Consequences

- The agent can only answer what the semantic layer defines; anything else goes to an honest refusal. Coverage is traded for correctness, and the baseline comparison measures that cost.
- Structured requests can be checked **before** any query runs.
- Messy-data rules live in one place (metric/dimension definitions), satisfying "consistent data rules".
- Unknown business terms ("GMV") map onto defined metrics or trigger a clarifying question.
- Open for design: config format, build in-house vs semantic-layer library, how hybrid questions chain a structured request into review search.

## Questions that drove this

- What is the worst failure for this user? (a silently wrong number)
- Which parts of the pipeline are most likely to go silently wrong, and who should own them: the model or us?
- What do we lose (coverage), and how will we measure that loss?
- What do real enterprise analytics agents do?
