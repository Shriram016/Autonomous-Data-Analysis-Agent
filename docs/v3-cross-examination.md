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

---

## Q2. If the database container crashes, is the data lost? Is this how production databases run?

*Raised 2026-10-19, during M0.5.*

**Short answer:** committed data is not lost. The container is only the Postgres program. The
data is in a Docker volume (files on disk). Before Postgres confirms a `COMMIT`, it writes the
change to the write-ahead log (WAL) on disk. After a crash, Postgres replays the WAL at startup.
M0.2 tested this: the containers were deleted and recreated, and the data stayed.

**When data is lost**

| Situation | Result |
|---|---|
| Container crashes, stops, or is deleted | Committed data is safe |
| Transaction not committed before the crash | That transaction is cancelled (all or nothing) |
| Volume deleted (`docker volume rm`, `docker compose down -v`) | All data lost |
| Disk fails or the machine is lost | All data lost, unless there is a backup |

**ADAA local setup vs typical production**

| Topic | ADAA now (local) | Typical production |
|---|---|---|
| Where it runs | One Docker container | Managed service (AWS RDS, Cloud SQL) or dedicated servers |
| Storage | Docker volume on local disk | Network disks, separate from the server, replicated |
| Copies | One | Primary + standby replicas, often in different data centres |
| Server failure | Data safe; service down until restart (`restart: unless-stopped`) | Automatic failover to a standby in ~30–120 s |
| Backups | Planned nightly `pg_dump` to S3 (G3) | Automatic snapshots + continuous WAL archiving |
| Restore point | Last nightly backup | Point-in-time recovery to any second |
| Restore test | Planned restore drill | Regular scheduled restore tests |
| Security | Localhost only, roles per job | Private network, encryption at rest and in transit, audit logs |
| Maintenance | Manual | Automatic patches in a maintenance window |
| Monitoring | Not yet | Alerts: disk, replication delay, slow queries, connections |

**Postgres in Docker in production?** Possible with Kubernetes and a Postgres operator (for
example CloudNativePG: replicas, failover, backups). Most small and medium teams use a managed
service, because the provider runs those parts.

**ADAA path:** local Docker → one EC2 server with Docker + nightly backups to S3 (documented
single point of failure) → move the database to AWS RDS Multi-AZ with point-in-time recovery.
Only the connection settings change; the application code stays the same.

**Interview one-liner (Q2):** "Durability comes from the WAL and from storage that outlives the
process; availability comes from replicas and failover; recoverability comes from backups you
have actually restored. ADAA has the first now, documents the gap in the second, and designs
the third."

---

## Q3. Real e-commerce orders arrive every second. Doesn't a daily load contradict that?

*Raised 2026-10-19, during M0.5. Extends Q1. Not locked.*

**Short answer:** no. A real company keeps two databases. The **production database (OLTP)**
takes orders in real time and must stay fast for customers. The **analytics copy (OLAP)** answers
heavy questions and is filled from production with a delay. ADAA reads only the analytics copy.
The orders change in real time in production; our copy shows the state "as of" the last load.
**Freshness is a separate choice:** how old may the copy be?

```
Shop app (thousands of users) → Production DB (OLTP) ──copy with delay──▶ Analytics copy (OLAP) ◀── ADAA reads
```

**Freshness options**

| Method | How it works | Delay | Cost / complexity |
|---|---|---|---|
| Daily batch (current ADAA design) | Copy new rows once a day | Up to 24 h | Low |
| Micro-batch | Same pipeline every 5–15 min | Minutes | Medium |
| Read replica | Live copy of the production DB | Seconds | Medium; no translations or topic tags; heavy queries still hit a copy of the production schema |
| CDC streaming (e.g. Debezium → Kafka) | Every insert / update / delete streams out as it happens | Seconds | High |
| Hybrid | Real-time counters for "today so far" + batch for history | Seconds for today | High |

**What changes in ADAA for a real-time source**

1. **Incremental load with a watermark:** load only rows changed since the last load, and merge
   them, instead of reloading and swapping every table.
2. **Upsert, not insert only:** an order moves from `shipped` to `delivered`, so existing rows
   are updated by primary key.
3. **Deletes:** a watermark on `updated_at` cannot see a deleted row. Options: soft delete (a
   `deleted_at` column) in the source, or CDC, which streams delete events ("tombstones").
4. **New reviews only:** translation, topic tags and embeddings run on new reviews in the
   background.
5. **Consistency:** each question records the watermark at start, so numbers and quotes come
   from the same moment (today's "data version" becomes a watermark).
6. **Caches:** clear only entries whose time range includes the new rows.
7. **Answers:** still show "Data as of …", now a time instead of a date.

**How copies decide insert / update / delete (first answer; deeper study in learning notes):**

| Method | What it reads | Insert / update / delete decided by |
|---|---|---|
| Physical replication (Postgres streaming replicas) | The primary's WAL, byte for byte | Nothing to decide: the replica replays the exact same changes, so it is an identical copy |
| Logical replication / CDC | Change events decoded from the WAL | Each event already says INSERT, UPDATE or DELETE, with the row's primary key |
| Watermark batch load | Rows with `updated_at` after the last load | New key → insert; existing key → update (upsert); deletes are invisible without a soft-delete flag |

**Recommendation (to decide in M3):** keep daily batch, because Olist is a snapshot, but build
ingestion as an **incremental load with a watermark and upsert** from the start. Then a move to
micro-batch or CDC changes only *when* the load runs, not *how* it works.

**Interview one-liner:** "Analytics never runs on the production database. Freshness is a dial,
from daily batch to CDC; ADAA uses daily batch for a snapshot dataset, but its ingestion is
incremental and keyed, so turning the dial changes the trigger, not the pipeline."

---

## Q4. Why not LiteLLM? Doesn't writing your own adapters mean code changes for every new provider?

**Short answer:** No. All code calls one function, `llm.complete(job, messages, form)`. Behind
it sit two adapters that use the official SDKs: `anthropic` (Claude) and `openai_compatible`
(OpenAI, Groq, DeepInfra, Together, Fireworks, Mistral, Gemini's OpenAI endpoint). A provider
change inside those two API styles is a config change (`adapter`, `base_url`, `model`,
`api_key_env`). Only a new API style needs code: one new adapter file of about 50 lines.

**Why not LiteLLM (decided 2026-10-20, ADR 0009 amended):**
1. Its main value is retry, fallback and a cost table. We build retry, fallback, breaker and
   rate limiter ourselves, on purpose, inside `llm.complete`.
2. We need two API styles, not 100+ providers.
3. Supply-chain risk: on 2026-03-24, two malicious LiteLLM releases on PyPI stole credentials and
   `.env` secrets. Fewer dependencies = smaller attack surface.
4. New provider features (adaptive thinking, strict JSON) arrive first in the official SDKs.

| Option | Pros | Cons |
|---|---|---|
| Official SDKs, two adapters (chosen) | Full control, newest features, few dependencies, easy to explain | Price per model kept in our config; new API style = new adapter |
| LiteLLM library | 100+ providers with no code, cost table, built-in fallback | Large dependency, supply-chain incident, many open bugs, features lag |
| any-llm (Mozilla) | Wraps official SDKs, light | Young, small community |
| Gateway server (Portkey, Bifrost, LiteLLM Proxy) | Budgets, logs, routing for many teams | A separate service to run; fits a large org, not this stage |

**When would I change my mind?** Many teams sharing many providers, with central budgets and
keys → a gateway. It still plugs in as one more adapter behind `llm.complete`.

**Interview one-liner:** "The port is ours; adapters are cheap. Two API styles cover almost every
provider, so swapping a model is a config line, and I didn't take on a dependency whose main
features I was building myself anyway."

---

## Q5. One LLM call takes 1–3 seconds. Isn't that too slow? How would you make it faster?

**Short answer:** 1–3 s is normal for one LLM API call; most of it is the model working. ADAA
measured ~1.8 s per call (3.5 s for the first, while a new schema was compiled and cached).

**Where the time goes (rough):** network round trip and TLS (~0.1–0.3 s), provider queue
(~0–0.3 s), reading the prompt (~0.3–0.6 s for ~1,560 tokens), writing the output one token at
a time (~0.3–0.7 s for 25–67 tokens), small extra for strict JSON.

**Why it is acceptable for ADAA:** a question is 1–3 LLM calls plus a fast SQL query, ~3–8 s
in total; progress streams to the screen (SSE), so the page never looks frozen; quick routes
answer simple cases with no LLM call.

| Lever | Gain | Cost |
|---|---|---|
| Stream the answer text | First words in < 1 s (perceived speed) | UI work |
| Faster provider (e.g. Groq) | Often several times faster output | Different model; check quality with evals |
| Shorter prompt / output | Less reading and writing time | Prompt work |
| Prompt caching | Faster reading of a long repeated prompt | Short prompts may not qualify |
| Fewer LLM calls per question | Largest gain | Design work (routing, quick routes) |

**What to measure:** total time per call (done) and **time to first token** (later, in
observability), per job and model, as p50 / p95, not averages.

**Interview one-liner:** "An LLM call is a few seconds by nature, so I design around it:
stream progress, skip the LLM where a rule can answer, cut calls per question, and measure
time-to-first-token at p95 before reaching for a faster model."

---

## Q6. What happens to a question if the worker crashes in the middle of it?

**Short answer:** it is not lost. ADAA proved this with a test: every worker process was
killed (SIGKILL) while a question was running; Celery put the job back on the queue, a new
worker process started, and the same job finished with the correct answer.

**How:** Celery removes a job from Redis only when the job finishes (`task_acks_late`), and
puts it back when the worker process dies (`task_reject_on_worker_lost`). If the whole
machine disappears, Redis gives the unfinished job to another worker after the visibility
timeout (300 s, longer than the slowest question, so a slow job is not run twice by mistake).

**The trade-off — "at least once":** a job can run twice (crash after the work, before the
acknowledgement). So tasks must be safe to repeat (idempotent). Answering a question only
reads data, so a repeat costs one extra LLM call and nothing else. Tasks that change things
(M5 actions) need an idempotency key so a repeat does nothing.

| Option | Pros | Cons |
|---|---|---|
| Acknowledge late (chosen) | No lost jobs | A job may run twice |
| Acknowledge early (Celery default) | Never runs twice | A crash loses the job silently |
| Checkpoints in Postgres (later, ADR 0011) | Resume from the last finished node, not the start | More code and storage |

**Interview one-liner:** "I chose at-least-once delivery and made the work safe to repeat;
I proved it by killing every worker mid-job and watching the same job finish on a new one."

---

## Q7. How do you know the agent gives right answers, and that a change didn't break it?

**Short answer:** an eval set of real questions with independently computed right answers, run
before every prompt, model or definition change. M1: 20 cases across every kind the agent
supports (simple, breakdown, period, filter, status, relative date, top, must-stop); first run
20 / 20, $0.01, about a minute.

**How it is built:** each case has the expected plan (the structured form) and hand-written SQL
straight from the tables. The SQL runs once and its answer is stored; each run compares the
agent's table with it (any order unless the question asks for a sort). Must-stop cases (a place
not in the data, a split the metric can't support) must stop with the right error. The plan is
compared field by field as a hint, never as the score — two plans can give the same answer.
Scoring is plain code, not an LLM judge, so it is exact, free and repeatable.

**Why not take the right answers from the system itself?** Then a compiler bug would be on both
sides and every case would still pass. Independent SQL tests the plan, the compiler and the
formatting at once.

| Option | Pros | Cons |
|---|---|---|
| Hand-written SQL answers (chosen) | Independent; exact; cheap to run | Writing and reviewing the SQL |
| Answers from our own compiler | Little work | Blind to compiler bugs |
| LLM judge | Handles open-ended text | Costs money, varies run to run, can be wrong |

**Limits:** 20 clear questions catch big regressions, not small ones; a 100% baseline is not
proof of quality. The set grows each milestone and gains hard cases (vague wording, follow-ups,
reviews, attacks), and every production bug becomes a new case.

**Interview one-liner:** "Every change runs against an eval set whose answers come from
hand-written SQL, not from the system under test; the plan is a diagnostic, the result is the
score, and the score is code, not another LLM."
