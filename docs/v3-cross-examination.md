# V3 cross-examination — system design and interview questions

> ⚠️ **Mandatory before V3 is called done** (see [v3-problem-statement.md](v3-problem-statement.md) §0,
> Next steps). Every component is cross-questioned until the answer is understood in detail.
> Questions are collected here as they come up during design and build; answers are written in
> plain words, with what we chose, pros/cons and alternatives. Nothing here is a locked decision
> unless it says so — locked decisions live in §0 and [adr/](adr/).

Question checklist to cover per component (at least): load and traffic growth · LLM fails · LLM
slow · caching (and when it's wrong) · retries · restart mid-question · sessions · storage, retention
and recovery · data growth.

---

## Q1. The orders table gets new rows every day — how does the system handle it?

*Raised 2026-10-18. Theory/interview question: Olist is a snapshot, so V3 only simulates this.*

**What our design does (daily batch):** once a day, ingestion loads new rows into staging →
validates → translates, tags and embeds **only the new reviews** (incremental) → publishes
atomically → data version goes up → caches are cleared.

**Pros**
- Simple and predictable; one validated, consistent snapshot per day (answers never mix days).
- LLM work (translate, tag, embed) happens once per new row, not per question — cheap.
- Caches stay valid all day.

**Cons**
- Data is up to 24 h old.
- Clearing all caches daily means a burst of cache misses (and cost) after each publish.
- The tables keep growing: queries slow down unless indexed, partitioned or pre-summarised.
- Changing the embedding model means re-embedding everything.

**What changes as the table grows**
- Indexes on the columns used for filters and joins (dates, state, category, seller).
- **Partitioning by month** — queries for 2018 only read 2018 partitions; old partitions can be archived.
- **Summary tables** (e.g. daily revenue by state × category) refreshed at publish — the locked
  "only if load tests show need" option.
- pgvector's HNSW index accepts inserts without a full rebuild; recall is monitored.
- Smarter cache invalidation: only drop cache entries whose time range touches the new days.

**Alternative approaches**

| Approach | How | Pros | Cons |
|---|---|---|---|
| Daily batch (ours) | One load + publish per day | Simple, consistent, cheap | Up to 24 h stale |
| Micro-batch | Same pipeline every 15–60 min | Fresher | More cache churn; more publishes to handle mid-question |
| Streaming / CDC | Changes streamed from the order system (e.g. Debezium → Kafka) as they happen | Near real-time | Much more complex; translation/embedding become async; answers can mix versions |
| Separate analytics warehouse | Copy production data into an OLAP store (read replica, ClickHouse, BigQuery, Snowflake) | Analytics never slows the live order system; built for big scans | Extra system and cost; still has a copy delay |
| Incremental summary tables / materialized views | Update only the affected summaries on each load | Fast reads at large scale | More moving parts; must stay consistent with raw tables |

**Interview one-liner:** "We chose daily batch with validate-then-publish because freshness of a day
is enough for managers' reporting questions, and it keeps answers consistent and cheap; if freshness
needs grew, we'd move to micro-batch, then CDC into a separate analytics store — and as data grows,
partitioning and summary tables keep queries inside the latency targets."

**Related open point (not locked):** with wake-on-demand the server is usually off, so a real daily
schedule would need a scheduled wake-up (vs catching up on wake, vs a replay clock that only moves
while the server is on).
