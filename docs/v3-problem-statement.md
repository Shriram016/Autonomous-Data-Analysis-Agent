# V3 Problem Statement

**Status:** 🔒 **Plan locked.** Problem definition complete. High-level decisions D1–D7 locked (sections 11–17);
D8: a minimal deployment is **core** (hosting and cost details decided in design). D9 (plan-first vs bounded agent loop) is open.
Next: data profiling, then detailed technical design.

> ⚠️ **Before designing or building V3, read [v3-requirements.md](v3-requirements.md)** — the
> non-functional requirements (load, latency, cost, availability, security, rate limits,
> observability). They must be considered up front and drive the design.
**Related:** [v2-polish-plan.md](v2-polish-plan.md) (V2 polish, done first; produces the frozen `v2.0` baseline)

---

## 0. Clean-slate design (started 2026-10-11)

V3 is being re-designed top-down (Level 0 → Level 1 → Level 2), one decision at a time, asking
"why this, why not that". **Sections 1–20 below are now a reference checklist, not locked
decisions** — each is re-decided here and only then counts as locked.

### Level 0 — Problem statement (🔒 locked)

> An AI agent that answers natural-language questions over a company's internal data, covering both
> structured records (tables) and unstructured text (such as customer reviews). It shows how it got
> each answer, asks when a question is unclear, and refuses when the data can't answer it. It runs
> as a deployed, multi-user service.

### Level 0 — Primary user (🔒 locked)

**A business manager with no SQL knowledge.** Asks in plain English and **cannot verify the
answer**, so trust is the central requirement: explain how each answer was computed, ask when
unclear, refuse rather than guess (a confident wrong number is worse than "I can't answer").
Rejected: data analyst (checks the SQL themselves, so trust behaviours become optional), executive
(summaries only, too narrow).

### Level 0 — Pain and value (🔒 locked)

Today a manager waits hours or days for an analyst to answer a routine data question, and
dashboards only answer questions someone predicted in advance. The agent gives a **trusted answer
to an unplanned question in seconds**. Value metric: **time to a trusted answer**. A change that
is faster but less trustworthy does not serve this pain.

### Level 0 — Read-only vs actions (🔒 locked, after dataset and question types)

**Business data is read-only.** One write action — flag a seller or create a task — saved only in
the agent's own tables, with manager approval first, logged, and undoable. Report export: later.
Details: [ADR 0002](adr/0002-read-only-business-data-one-approved-action.md).

### Level 1 — Dataset criteria (🔒 locked)

Must-have: (1) real company data, not synthetic/teaching; (2) several related tables needing
joins; (3) real mess (missing values, duplicates, lookup codes); (4) customer text from the same
business, linked to the records. Preferred: (5) questions a manager would really ask; (6) workable
size (laptop, free/cheap API tiers); (7) license allows a public portfolio repo; (8) room for
actions the agent could plausibly take.

### Level 1 — Dataset (🔒 locked)

**Olist Brazilian E-Commerce.** Only candidate meeting all must-haves; reviews linked to orders.
Details, rejected alternatives and consequences: [ADR 0001](adr/0001-olist-dataset.md).

### Level 1 — Question types (🔒 locked)

Two independent axes. **Context:** (A) standalone; (B) follow-up — rewritten into a standalone
question using earlier turns, then handled as usual.

**Need** (all checked against Olist):

| # | Type | Example | Expected behaviour | Scope |
|---|---|---|---|---|
| 1 | Numbers | "Late-delivery rate by seller in 2017?" | Query tables, answer, explain computation | Core |
| 2 | Review text | "What do customers complain about?" | Search reviews, summarise, cite | Core |
| 3 | Hybrid | "Worst categories for late delivery, and what do those customers say?" | Numbers → reviews filtered by that result → one answer | Core |
| 4 | Ambiguous | "Who are our best customers?" | Ask or state the assumption | Core |
| 5 | Unknown business term | "What's our GMV?" | Map to a defined metric or ask | Core |
| 6 | Unanswerable (incl. false premise) | "What's our profit?" (no cost data) / "Why did sales drop in 2019?" | Refuse naming the missing data, or correct the premise | Core |
| 7 | Off-topic | "Write me a poem" | Decline, say what it can do | Core |
| 8 | Metadata | "What date range is the data?" | Describe data and capabilities | Core |
| 9 | Personal data request | "List customer IDs and zip codes" | Refuse (Olist is anonymised, but IDs/zip prefixes are quasi-identifiers) | Core |
| 10 | "Why" / forecast | "Why did reviews drop in March?" | Decide after core works (can show associations, not prove causes) | Later |

Prompt injection is a safety concern, not a question type — handled separately.

### Level 0 — Success criteria (🔒 locked)

Broad goals; each gets one or more eval metrics (formula, test questions, pass mark) in the eval
design step. Every failure is labelled with its **cause** (e.g. routing, retrieval), not blended
into one pass rate.

| # | Criterion | Measured as (detail in eval design) |
|---|---|---|
| S1 | Correct numbers | % of number questions answered correctly |
| S2 | Correct review answers | Right reviews found; summary says only what they say |
| S3 | Right source chosen | % routed correctly to numbers / reviews / both |
| S4 | Asks when unclear | Asks on ambiguous questions, not on clear ones |
| S5 | Refuses when it should | Refuses unanswerable / off-topic / personal-data, not answerable ones |
| S6 | Never silently wrong on messy data | No wrong numbers on known data traps |
| S7 | Explains every answer | Every answer has "how this was computed" |
| S8 | Safe actions | No action runs without approval |
| S9 | Production targets met | Latency, cost, load targets (set in the requirements step) |

### Level 0 — Non-goals (🔒 locked)

- A general "chat with any database" product — one realistic company dataset, done properly.
- Editing business data ([ADR 0002](adr/0002-read-only-business-data-one-approved-action.md)).
- Interface languages other than English (Portuguese reviews are handled internally).
- Live/streaming data — Olist is a snapshot; at most a simulated daily refresh.
- Fine-tuning models.
- Anything from the builder's employer work.

Whether the LLM may write SQL is **not** a Level 0 rule — it is a Level 1 architecture decision.

**Level 0 complete.**

### Level 1 — Usage scenario (🔒 locked, may be revisited during design)

Olist's internal analytics assistant: **500** registered managers; **~20** concurrent normally;
**~100** at peak (Monday reporting) — the design point, where speed targets must hold; **200**
spike — survive only (queue or polite "busy", never crash or wrong answers, speed not required).
~1 question/min per active user at peak → **~1.7 questions/s**, **~5–7 LLM calls/s**. Free LLM
tiers can't sustain that — deliberately, so caching, cheaper models and queuing become design work.

### Level 1 — Speed targets (🔒 locked)

Targets hold at the **100-user peak**. p50 = half of answers faster; p95 = 19 of 20 faster.

| Measure | p50 | p95 |
|---|---|---|
| **Time to first feedback** (any progress shown, e.g. "Searching reviews…") | < 1s | < 2s |
| **Total time** — clarify / refuse / off-topic / metadata | < 2s | < 4s |
| **Total time** — numbers | < 5s | < 10s |
| **Total time** — review text | < 6s | < 12s |
| **Total time** — hybrid | < 10s | < 20s |

**Tracked, no target (diagnostics):** time to first answer token (TTFT), output speed (tokens/s),
per-step time (router, planner, database, review search, each LLM call), queue wait, p99.
**Why first feedback, not TTFT:** the agent routes, plans and queries before writing, so the first
answer token arrives late; progress messages are what the manager sees first. Implies streaming
progress to the UI.

### Level 1 — Cost target (🔒 locked as a soft baseline)

**Baseline: < $0.01 per question on average** (~55k questions/month → ~$550/month). A soft
baseline, not a fixed limit — reviewed after first measurements. Cost tracked per question type
(hybrid will cost more). Business framing: an analyst answering the same question costs dollars.

### Level 1 — Failure behaviour and uptime (🔒 locked)

| Failure | Required behaviour |
|---|---|
| LLM provider down / rate-limited | Switch to a backup model or provider; else a clear error — **never a made-up answer** |
| Database down | Clear error; never a partial or old answer presented as current |
| Anything slow | Every external call has a time limit; each question has an overall time cap |
| Uptime | 99.5% during business hours (≈40 min/month), measured in load tests and the demo period |

Rule: an honest error beats a confident guess. The backup-provider requirement implies LLMs are
called through one owned interface, not tied to a vendor (V2's single-vendor coupling hid a
deprecated-model failure).

### Level 1 — Security and privacy (🔒 locked)

Core:
1. Every manager logs in; every request is tied to a person (audit, per-user limits, approvals).
2. Least privilege in the database: read-only on business data; narrow write only to agent-owned
   tables ([ADR 0002](adr/0002-read-only-business-data-one-approved-action.md)).
3. No personal data in answers or logs beyond what's needed (customer IDs, zip codes masked).
4. Prompt-injection resistance, including instructions hidden inside review text — reviews are
   untrusted input entering prompts; needs a written threat model and defences.

Parked (stretch): role-based data access (e.g. regional manager sees only their region).

### Level 1 — Overload and abuse controls (🔒 locked)

1. **Per-manager quota** — start at 30 questions/hour.
2. **Global concurrency limit** — at most N questions in progress; the rest queue.
3. **Provider rate limits enforced centrally** — one place counts LLM calls/min and holds back
   before the provider's limit (most common way LLM apps fail under load).
4. **Polite rejection** — "hourly limit reached, try in 12 min" / "busy, you're #3 in queue".

Numbers are starting values, tuned during load testing.

### Level 1 — Data requirements (🔒 locked)

1. **Daily freshness** — new orders and reviews loaded, translated and searchable within 24h
   (simulated by replaying the snapshot day by day): an ingestion pipeline, not a one-off script.
2. **Growth headroom** — speed targets hold at 10× today's data (synthetic scale-up, test only).
3. **Consistent data rules** — messy-data handling defined once, applied to every answer (protects S6).

### Level 1 — Observability (🔒 locked)

1. **Every question traced end to end** — route, each step, reviews retrieved, every LLM call
   (prompt, tokens, cost, time), outcome.
2. **Dashboard** — p50/p95 per question type, error rate, cost per question, question-type mix,
   cache hit rate, quota rejections.
3. **Alert conditions defined** — e.g. p95 above target for 10 min, error rate > 2%, cost per
   question > 2× baseline.
4. **Manager feedback** — 👍/👎 per answer, linked to its trace; bad answers become new test questions.

**Non-functional requirements complete** (scenario → observability above). These supersede the
draft in [v3-requirements.md](v3-requirements.md).

### Level 1 — How numbers are computed (🔒 locked)

**Semantic layer.** We define metrics, dimensions, joins and messy-data rules once; the LLM only
fills a structured request, which code validates and compiles to SQL. Text-to-SQL is built as the
comparison baseline. Details: [ADR 0003](adr/0003-semantic-layer-for-numbers.md).

### Level 1 — Database (🔒 locked)

**PostgreSQL** — the database enforces least privilege and query time limits; handles 100
concurrent users. Rejected DuckDB (no permissions) and SQLite. [ADR 0004](adr/0004-postgresql.md).

### Level 1 — Portuguese reviews (🔒 locked)

**Translate once at load time** (part of the ingestion pipeline, never at question time); store
both versions; search the English. Direct-Portuguese-search comparison: nice-to-have (stretch).
[ADR 0005](adr/0005-translate-reviews-at-load-time.md).

### Level 1 — Review search (🔒 locked)

**Hybrid search** (PostgreSQL full-text + vector similarity), vectors in **pgvector** — chosen on
its own merits: filtering by order data in one query, scale fit, no sync, one security boundary.
[ADR 0006](adr/0006-hybrid-review-search-in-pgvector.md).

### Level 1 — Agent shape (🔒 locked)

**Bounded loop:** pick an allowed tool → see result → next step, with a hard step limit, allowed
tools only, and a check after each step; pauses for approval before actions. Plan-first built as a
comparison. [ADR 0007](adr/0007-bounded-agent-loop.md).

### Level 1 — Routing (🔒 locked)

Follow-up rewrite → **separate router** → (early exit for clarify / refuse / off-topic / metadata)
or bounded loop with only that route's tools. Classifier type: Level 2.
[ADR 0008](adr/0008-separate-router.md).

### Level 1 — LLM interface (🔒 locked)

All code calls one owned `llm.complete(job, ...)`; **LiteLLM** behind it (providers, fallback, cost).
Model per job + fallback chain in config, chosen by evals.
[ADR 0009](adr/0009-llm-interface-litellm-behind-owned-port.md).

### Level 1 — Service shape (🔒 locked)

**Backend API + durable job queue + workers; UI is a client** with streamed progress. Why:
approval pauses, durability across restarts, spike handling, one place for login/quotas/tracing;
plus the learning goal. [ADR 0010](adr/0010-backend-service-with-job-queue.md).

### Level 1 — Agent framework (🔒 locked)

**LangGraph**, checkpoints in PostgreSQL (approval pause, resume after restart, step limits).
**No RAG framework** — review search is plain SQL. [ADR 0011](adr/0011-langgraph-no-rag-framework.md).

### Level 1 — Guardrails (🔒 locked)

One separate layer, three points: **before** (off-topic, personal data, injection), **during**
(validate structured request; review text marked untrusted), **after** (every number must appear
in the query result, quotes must match reviews, personal data masked — else block/retry). Code
first, LLM judge only where needed. [ADR 0012](adr/0012-guardrails-layer-three-points.md).

### Level 1 — Short-term memory (🔒 locked)

Last ~5 turns as question + structured request + one-line summary; big results stored and
referenced by ID; older-turn summary only if tests show a need.
[ADR 0013](adr/0013-short-term-memory-compact-turns.md).

### Level 1 — Long-term memory (🔒 locked, core)

Only **preferences the manager explicitly asks to save**; per manager, viewable and deletable;
any preference used is stated in the answer's explanation. No automatic memory.
[ADR 0014](adr/0014-long-term-memory-explicit-preferences.md).

### Level 1 — Observability tools (🔒 locked)

**Langfuse Cloud** (LLM traces, cost, prompt versions; not self-hosted — too heavy for one VM) + **Grafana Cloud** (hosted Prometheus-style metrics) (system metrics,
dashboard, alerts), both fed via **OpenTelemetry**. [ADR 0015](adr/0015-langfuse-plus-prometheus-grafana.md).

### Level 1 — Caching (🔒 locked)

**(a) Result cache** keyed on the structured request (different phrasings → same request → same
hit) + **(b) exact-question cache**. All caches cleared at each daily data refresh. Rejected for
core: similar-meaning (semantic) cache — "revenue in SP" ≈ "revenue in RJ" can return a wrong
answer; stretch only, behind a strict check.

### Level 1 — UI (🔒 locked)

**React single-page app (Vite + TypeScript)**, thin client of the backend; login and per-manager
screens. [ADR 0016](adr/0016-react-ui.md).

### Level 1 — Deployment (🔒 locked, provisional)

**AWS EC2** for now — one VM running the same Docker Compose as local. Better options (managed
services, CI/CD, Terraform) explored after development is complete. Known weakness: one machine
is a single point of failure — documented, with a scale-up path.

**Running mode (locked for now, revisit after development): wake on demand.** The React UI is
hosted as static files on free hosting (always on). While the backend sleeps, the page shows
"Demo is asleep — wake it up (~2–3 min)" plus demo video and screenshots. The wake button calls a
small serverless function (AWS Lambda) that starts the EC2 server; the UI polls a health endpoint
and shows startup progress; the server auto-stops after ~30 min idle. Guards: wake-up limit per
day + bot check, guaranteed auto-stop, AWS budget alarm. Wake comes before login (Keycloak is on
the server). Cost ≈ server hours + ~$3–5/month disk/IP. Alternatives for later: Oracle Cloud
always-free ARM (24 GB, $0, not AWS), Hetzner (~€7–10/month), serverless redesign.
Consequence for containers: the proxy no longer serves the UI files, only `/api` and `/auth`.

### Level 1 — Eval structure (🔒 locked)

- **~150 test questions**, builder-written across all 9 types + follow-ups + attacks (LLM drafts
  allowed, every one human-reviewed); written incrementally as each part is built.
- **Ground truth:** numbers = hand-written SQL independent of the semantic layer; reviews =
  hand-labelled relevant reviews; clarify/refuse = expected route.
- **60/40 dev / held-out split** — tune on dev, report held-out only.
- **3 runs per question** — report mean and "passes all 3" (pass^k).
- **Failure-cause label** per failure (router, request, retrieval, guardrail, answer, …).
- **CI gate:** fast subset on every code/prompt change; full set before releases.
- Eval tool (own harness / DeepEval / Ragas / Langfuse datasets): decided later.

### Level 1 — LLMOps (🔒 locked, all mandatory)

- **Prompts versioned in git** (source of truth; Langfuse may display them); every trace records
  prompt version + model.
- **Model-per-job config** in a versioned file, never hard-coded.
- **Release rule:** a prompt or model change merges only if the CI eval subset passes within a set
  tolerance; full eval before a release.
- **Side-by-side comparison** old vs new, per question type, incl. cost.

### Level 1 — Testing beyond evals (🔒 locked)

| Level | Checks | LLM | When |
|---|---|---|---|
| Unit | One piece alone (SQL compilation, number-check guardrail) | No | Every change |
| Integration | Real PostgreSQL/Redis in Docker (read-only role can't write, job survives restart, approval resumes) | Faked | Every change |
| End-to-end | Key flows through the API (login → ask → stream → answer) | A few | Before release |
| Failure injection | LLM timeout → backup; DB down → clear error | No | Before release |
| Load test | Speed at 100 users, survival at 200 (Locust/k6) | Yes | Before release |

### Level 1 — Single agent (🔒 locked, revisit if needed)

**One agent** (router + bounded loop with route-specific tools), not multi-agent. Revisit if the
task grows much broader. [ADR 0017](adr/0017-single-agent-not-multi-agent.md).

### Level 1 — Login (🔒 locked)

**Self-hosted Keycloak (OIDC)**; backend only verifies JWTs. No cloud/vendor lock-in; accounts in
our own database. [ADR 0018](adr/0018-keycloak-self-hosted-login.md).

### Level 1 — Data sent to LLM providers (🔒 locked, gap G1)

**Approved providers only** (no training on our data; fallbacks too); **send the minimum**
(definitions + summarised results); **masking function inside `llm.complete`** — one door, also
cleans logs/traces; personal/confidential list in a versioned config.
[ADR 0019](adr/0019-llm-data-sharing-approved-providers-masking.md).

### Level 1 — Answer format (🔒 locked, gap G2)

Plain-English answer + **table + chart**. **Code chooses the chart by rules** from the structured
request (time dimension → line, category → bar, single number → stat card); the manager may
override from a **fixed list** only; the chart is always drawn from the actual query result. The
LLM never writes chart code. Rejected: text only (poor for trends); LLM-written chart code (breaks
"no free-form code", can plot wrong data).

### Level 1 — Backup and recovery (🔒 locked, gap G3: design core, implementation stretch)

**Design:** nightly `pg_dump` of all PostgreSQL data (business tables, translations + embeddings,
agent tables, preferences, conversations/checkpoints, feedback, Keycloak, Langfuse) to encrypted
S3; retention 7 daily + 4 weekly; **RPO 24h, RTO < 1h** (incl. vector index rebuild); restore
drill on the test list. Not backed up: Prometheus metrics, Redis queue/caches (temporary); code,
prompts, semantic layer, config, eval sets are in git. Upgrade path: managed DB with
point-in-time recovery (RDS). Building it is a stretch goal.

**Data inventory:** Olist tables · translations + embeddings · agent tables (flags, tasks, audit
log) · saved preferences · conversations (checkpoints, turn records, stored results) · feedback ·
Keycloak accounts · Langfuse traces · Prometheus metrics · Redis queue/caches · git-held config.

### Level 1 — Retention (🔒 locked, gap G3b; starting values)

| Data | Retention |
|---|---|
| Conversations (turns, stored results) | 90 days, then auto-deleted |
| Paused approvals never confirmed | Expire after 7 days (safety: stale actions never run) |
| Traces (Langfuse) | 30 days |
| Traces linked to 👎 feedback | Kept (masked) until reviewed / turned into eval cases |
| Audit log of actions | 1 year |
| Manager deletes a conversation | Removed immediately (audit log excepted) |

Enforced by a scheduled cleanup job; stated in the README.

### Level 1 — Daily data validation (🔒 locked, gap G4)

**Validate, then publish.** New data lands in staging; checks run (expected columns, row counts in
normal range, no duplicate IDs, valid dates, valid joins, non-empty translations); only a fully
passing batch is published to live tables. On failure: batch held, alert fires, answers keep using
yesterday's good data. **Answers show data freshness** ("data as of 12 Oct"). Rules come from data
profiling. Check tool (plain SQL / Great Expectations / Pandera): Level 2. Rejected: load-and-hope;
load-then-flag (suspicious data still reaches answers).

### Level 1 — Environments and secrets (🔒 locked for now, gap G5)

**Environments:** local (Docker Compose) + production (EC2); staging documented as the next step.
**Secrets:** git-ignored `.env` for now. A secrets manager (e.g. AWS SSM Parameter Store, behind
one small function) and a CI secret scan are revisited with the other deployment decisions.

### Level 1 — Semantic-layer versioning (🔒 locked, gap G6)

Git keeps the history; the **running system** must also know the version. The semantic layer
carries a version (number or automatic content hash); every answer records which version computed
it; a version change **clears the result cache** and CI **flags eval questions** using changed
metrics for review. Definition changes go through the same CI gate as prompt changes. Rejected:
just editing the file (stale caches, misleading evals, unexplainable old answers).

### Level 1 — Escalation to an analyst (🔒 locked, core, gap G7)

On a refusal or 👎, the manager can **"Send to analyst"**: creates a **task** (existing action
type, [ADR 0002](adr/0002-read-only-business-data-one-approved-action.md)) holding the question,
what the agent tried and why it stopped. Escalations double as a to-do list for extending the
semantic layer and a source of new eval questions. Real Slack/Jira/email integration: stretch.

### Level 1 — MCP (🔒 locked, stretch)

An MCP server would be another thin client of the backend API (agent / semantic-layer tools usable
from Claude Desktop, IDEs). No core design change. Shown as a future client; built after core.

> **Gap check (2026-10-11)** against wider production-AI-agent topics found: G1 data sent to LLM
> providers ✅; G2 answer format (charts/tables) ✅; G3 backup and recovery ✅; G3b conversation retention ✅; G4 validating each day's
> new data ✅; G5 environments and secrets ✅; G6 semantic-layer changes (cache/evals/preferences) ✅;
> G7 escalation to a human analyst ✅. **All gaps closed — Level 1 decisions complete.** **Parked for Level 2:** streaming protocol, ingestion
> scheduler, relative-date resolution against 2016–18 data, LLM-judge vs human check, API
> versioning, runbooks.

### Level 1 — Containers (🔒 locked for now)

On the EC2 server (8 GB instance; ~4.5–5.5 GB in use):

| # | Container | Role | Runs |
|---|---|---|---|
| 1 | proxy (Caddy/Nginx) | HTTPS, routes `/api` → api, `/auth` → keycloak (React UI is on free static hosting) | Always |
| 2 | api (FastAPI) | Token check, quotas, queue jobs, stream progress, approvals, feedback | Always |
| 3 | worker ×2+ | LangGraph agent (same image as api, different start command) | Always |
| 4 | postgres + pgvector | business / agent / conversation / staging schemas + Keycloak's own database | Always |
| 5 | redis | Job queue, progress pub/sub, caches, rate-limit counters | Always |
| 6 | keycloak | Login (OIDC) | Always |
| 7 | otel-collector | Pushes metrics/traces to Grafana Cloud and Langfuse Cloud | Always |
| 8 | ingestion | Daily replay → validate → translate → embed → publish; exits | Daily |
| 9 | housekeeping (optional) | Nightly backup → S3, retention cleanup; build decided later | Scheduled |

Outside the server: React UI (free static hosting), wake-up function (AWS Lambda), Langfuse Cloud,
Grafana Cloud, LLM providers (via LiteLLM), S3, GitHub Actions.

### Level 1 — Architecture views (Views 1–2 ✅ reviewed; View 3 flows pending)

Notes from review: scheduled housekeeping jobs (nightly backup, retention cleanup) are **part of
the design; whether to implement them is decided later**. Router and loop internals: Level 2.
Progress reaches the UI as a stream of events (submit → job ID → event stream; likely SSE, Level 2).

> **Next steps (in order, as of 2026-10-12):**
> 1. **View 3 — flows:** walk each route through the components, one at a time: numbers →
>    reviews → hybrid → clarify/refuse/off-topic → follow-up → action with approval. Then check
>    every locked requirement has a home in the picture.
> 2. **Scope and time check → milestone plan** (old §19 is reference only; it lacks Keycloak,
>    queue/workers, React, wake-on-demand, etc.). Decide weeks available and the smallest
>    impressive version.
> 3. **Repo and codebase plan:** reuse V2 code or fresh; folder layout (backend / frontend /
>    infra); tooling (Python version, package manager).
> 4. **Start M0 with data profiling** (also verifies Olist license and review-text counts).
>
> Session style: one question at a time, recommendation + options, lock, record here (+ ADR when
> hard to reverse, surprising, and a real trade-off), terms in [GLOSSARY.md](../GLOSSARY.md).

**View 1 — Big picture (who and what the system touches)**

```mermaid
flowchart LR
    M([Manager]) -- questions, approvals, feedback --> S[ADAA V3]
    S -- answers, charts, explanations --> M
    S -- masked prompts --> L[(Approved LLM providers)]
    D[(Olist data, daily replay)] --> S
    S -- escalation tasks --> A([Analyst])
    B([Builder / operator]) -- dashboards, alerts, traces --> S
    F([Future: MCP clients]) -.-> S
```

**View 2 — Components inside**

```mermaid
flowchart TB
    UI[React UI] -- login redirect --> KC[Keycloak]
    UI -- REST + progress stream, JWT --> API[Backend API<br/>token check · quotas · concurrency limit<br/>approvals · feedback]
    API -- verify token --> KC
    API -- enqueue job / read progress / caches --> R[(Redis<br/>job queue · progress pub/sub<br/>result + exact-question caches<br/>rate-limit counters)]
    R --> W

    subgraph W[Workers — LangGraph agent]
        FR[Follow-up rewrite] --> GI[Guardrails: before]
        GI --> RT[Router]
        RT -- clarify / refuse / off-topic / metadata --> ANS
        RT -- numbers / reviews / hybrid --> LP[Bounded loop<br/>route tools only · step limit]
        LP -- structured request --> SL[Semantic layer<br/>validate + compile SQL]
        LP --> RS[Review search<br/>full-text + pgvector]
        LP -- proposed action --> AP[Approval pause]
        LP --> GO[Guardrails: after<br/>numbers · quotes · masking]
        GO --> ANS[Answer + chart spec + explanation]
    end

    W -- all LLM calls --> LLM[llm.complete<br/>masking · rate limiter · LiteLLM · fallback]
    LLM --> EXT[(LLM providers)]
    SL -- read-only role --> PG
    RS -- read-only role --> PG
    AP -- agent-write role --> PG
    W -- checkpoints, turns, stored results --> PG

    subgraph PG[PostgreSQL + pgvector]
        BIZ[business schema<br/>Olist tables · reviews + translations + embeddings]
        AG[agent schema<br/>flags · tasks · audit · preferences · feedback]
        CONV[conversation state<br/>checkpoints · turns · stored results]
        STG[staging schema]
    end

    ING[Ingestion pipeline — daily<br/>replay → staging → validate → translate → embed → publish<br/>clears caches] --> STG
    ING -- translate / embed calls --> LLM
    ING --> BIZ

    W & API -. OpenTelemetry .-> OBS[Langfuse — LLM traces<br/>Prometheus + Grafana — metrics, alerts]
    JOBS[Scheduled jobs<br/>nightly backup → S3 · retention cleanup] --> PG
    CI[CI: unit + integration tests · eval subset gate] -.-> W
```

---

## 1. Why V3 exists

V1 and V2 answer questions about **one clean CSV** (Sample Superstore). The engineering is solid
(planner → constrained tools → critic → fix/replan → answer, LangGraph, session memory, Langfuse,
63-query eval), but the **problem itself reads as a toy**: one table, clean data, and a well-known
Kaggle teaching dataset.

The aim of V3 is a project whose **first impression**, for a recruiter or hiring manager reviewing a
mid-level / lead AI engineer candidate, is:

> *"This person knows how to build a production AI agent system end-to-end."*

The research bar this is measured against says a project reads as hire-worthy when it makes the
builder's **judgment under failure** visible:

1. Failure modes anticipated and designed against, not just patched.
2. Evaluation separated by failure type, not one blended number.
3. Explicit rejected alternatives, backed by evidence.
4. Contact with messier, real-world data, not a curated demo.

V2's eval already showed the key lesson that motivates V3: **data agents fail on meaning, not
structure.** V3 takes that lesson into a realistic setting.

---

## 2. Goal (one line)

**Build an AI agent that answers a business manager's questions over a real, messy company's data
(structured records and customer text) correctly, and knows when it can't.**

## 3. Goal (one paragraph)

An AI agent for a business manager that answers questions over a real, messy e-commerce company's
data. It **routes** each question to the right source (a SQL database for numbers, a vector store
of customer reviews for opinions, or both), **shows how it got the answer**, **asks** when a
question is unclear, and **refuses** when it can't answer. Every claim about the system is backed
by evals broken down by failure type and compared against V2 and a simple baseline.

---

## 4. The user

**A business manager with no SQL knowledge.**

- Asks questions in plain business language, often vague ("best customers", "recently", "doing badly").
- Can't check a SQL query or a pandas plan, so they need the answer, a plain-English explanation of
  how it was computed, and any assumptions stated clearly.
- A confident wrong number is worse for them than "I can't answer that" or a clarifying question.

This choice makes **trust** the central product requirement: correctness, transparency, ambiguity
handling and honest refusal matter more than speed or breadth.

---

## 5. What V3 must handle: question types

| Type | What it needs | Example (assuming an e-commerce dataset) |
|---|---|---|
| **Structured (numbers)** | Querying and joining multiple related tables | "What was revenue by state last quarter?" / "Which sellers have the highest late-delivery rate?" |
| **Unstructured (opinions/text)** | Retrieval over customer review text (RAG) | "What do customers complain about most?" |
| **Hybrid (both)** | Numbers and text, combined into one answer | "Which product categories have the worst late-delivery rates, and what are customers saying about them?" |
| **Ambiguous** | Detecting the ambiguity; asking or stating an assumption | "Who are our best customers?" (by revenue? order count? profit?) |
| **Unanswerable** | Recognizing missing data or capability; refusing honestly | "What's our marketing spend per channel?" (data doesn't exist) |
| **Follow-up (multi-turn)** | Resolving context from earlier turns | "What about Rio de Janeiro?" |

### The data must be messy for real

The chosen dataset must contain **real-world data quality problems**, not artificially injected
ones where possible: missing values, inconsistent or duplicate records, codes that need lookup
tables, confusing column meanings. Dirty data must never silently produce a wrong number.

---

## 6. Success criteria

V3 is successful when each of these is **demonstrated with measured evidence**:

| # | Criterion | What "done" looks like |
|---|---|---|
| S1 | **Correct on structured questions** | Measured accuracy on multi-table questions with known ground truth |
| S2 | **Correct on text questions** | Retrieval and answer quality measured separately (did it find the right reviews? did it summarize them faithfully?) |
| S3 | **Correct routing** | Measured accuracy of choosing SQL vs RAG vs both |
| S4 | **Robust to messy data** | Data quality issues are handled or flagged, never silently wrong |
| S5 | **Handles ambiguity** | Asks or states its assumption on ambiguous questions instead of guessing |
| S6 | **Knows its limits** | Refuses unanswerable questions rather than inventing answers |
| S7 | **Transparent** | Every answer comes with a plain-English explanation of how it was computed |
| S8 | **Failure-cause eval** | Every failure classified by cause and responsible component, not one pass rate |
| S9 | **Compared against alternatives** | Results compared against a text-to-SQL baseline (D6) and the translation alternative (D2); router comparison low priority (D5). No direct V2 comparison — see section 17 |
| S10 | **Production-shaped** | Built and run like a real system (see section 7) |

---

## 7. Production qualities (principles, not design)

These are the qualities that create the "production system" impression. *How* each is built is
decided in the design phase, not here. **Measurable targets for each quality (load, latency, cost,
availability, etc.) are in [v3-requirements.md](v3-requirements.md).**

| Quality | Meaning |
|---|---|
| **Safe by design** | The agent can only read data, never change it. Bounded queries, timeouts, resistance to prompt injection (including from review text) |
| **Reliable** | Guardrails catch wrong or unsupported answers. Clarify or refuse rather than guess |
| **Measured** | Evals with failure-cause breakdown, runnable automatically; regressions are caught |
| **Observable** | Every request traced end-to-end (route, steps, retrieval, cost, latency, failures) |
| **Cost-aware** | Per-query cost and latency tracked; right-sized models per step |
| **Service-shaped** | Usable as a service, with the UI as one client of it |
| **Improves from use** | User feedback captured and convertible into new eval cases |

A minimal deployment is core (D8). The hosting choice and its cost are decided in the design phase.

---

## 8. Relationship to V2

- **Same project, next version.** Same repo, new branch. V2 is tagged `v2.0` first.
- **Architecture carries forward and extends**: planner → constrained tools → critic → fix/replan →
  answer. New: multiple tables, a RAG path, a router between them, and semantic guardrails.
- **The core principle stays:** no free-form code generation in the product. Direct LLM code/SQL
  generation is the **baseline V3 is compared against**, not the product.
- **V2's measured failures feed V3's design** (from the V2 polish failure-cause breakdown).
- The README tells one evolution story: V1 proved the idea → V2 added orchestration, memory and
  evals, and showed failures are semantic → V3 tackles real messy multi-source data with semantic
  guardrails and routing.

---

## 9. Out of scope for V3

- A general "chat with any database" product. V3 targets **one realistic company dataset**, done properly.
- Write operations of any kind (no inserts, updates, deletes).
- Free-form code or SQL generation as the product's execution method.
- Features added for their own sake that don't serve the success criteria.
- Hosting and cost details (decided in design). A minimal deployment itself is in scope (D8).
- Employer-related work (e.g. invoice extraction) stays entirely separate from this project.

---

## 10. Open decisions (to be discussed next)

| # | Decision | Current leaning |
|---|---|---|
| D1 | **Dataset** | ✅ **Locked: Olist** — see section 11 |
| D2 | **Portuguese review handling** | ✅ **Locked: translate at load time, validated against direct Portuguese search** — see section 12 |
| D3 | **Database engine** | ✅ **Locked: PostgreSQL** — see section 13 |
| D4 | **Vector store and embedding model** | ✅ **Locked: pgvector inside PostgreSQL**; embedding model chosen later by test — see section 14 |
| D5 | **Router design** (how a question is classified as SQL / RAG / hybrid) | ✅ **Locked: separate router step before planning** — see section 15 |
| D6 | **Tool layer for multi-table queries** (how constrained tools extend to joins) | ✅ **Locked: semantic (business) layer; text-to-SQL as core baseline** — see section 16 |
| D7 | **Eval design** (question set, ground truth, per-path metrics) | ✅ **Locked** — see section 17 |
| D8 | **Deployment** | ✅ **Minimal deployment is core** (needed to verify load, latency and availability targets). Hosting choice and cost details: decided in design |
| D9 | **Plan-first vs bounded agent loop** (and human approval) | **Open.** V3 inherits plan-first from V1/V2; D5 rejected a free-roaming loop by reasoning, not by test. Candidates: plan-first, bounded loop (step cap), plan-then-adapt, or route by question type. Decide by a comparison test on the same questions (accuracy, cost, latency). **Note:** V3 is read-only, so the approval step needs a real trigger, e.g. confirming an assumption on a vague question, an expensive query, or an export containing personal data |
| — | **Non-functional requirements** | Draft in [v3-requirements.md](v3-requirements.md) — review before design |

---

## 11. Decision D1 — Dataset: Olist Brazilian E-Commerce (locked)

**Dataset:** [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
— real, anonymized data from Olist, a Brazilian marketplace. About 100k orders, 2016–2018,
9 related CSV tables: orders, order items, customers, sellers, payments, products, order reviews,
geolocation, product category name translation. License: CC BY-NC-SA 4.0.

### Requirements it was judged against

| # | Requirement | Olist |
|---|---|---|
| R1 | Real-world, not synthetic | ✅ Real company data, anonymized |
| R2 | Multiple related tables needing joins | ✅ 9 tables |
| R3 | Real data quality problems | ✅ Missing delivery dates and categories, duplicate geolocation rows, Portuguese category names needing a lookup table |
| R4 | Customer text from the same business | ✅ Order reviews (1–5 score + comment), linked to orders |
| R5 | Business-manager friendly | ✅ Sales, delivery, sellers, satisfaction |
| R6 | Workable size (laptop, free API tiers) | ✅ ~100k orders |
| R7 | License allows a public portfolio repo | ⚠️ CC BY-NC-SA 4.0: fine for non-commercial portfolio use with attribution |

### Alternatives considered and rejected

| Dataset | Rejected because |
|---|---|
| Superstore (normalized) | Well-known teaching dataset; synthetic-feeling; carries the "tutorial" first impression |
| Yelp Open Dataset | Review-platform data, not a company's internal data; consumer-style questions; millions of reviews need heavy subsetting; more restrictive terms |
| H&M Fashion Recommendations | Only 3 tables; no customer opinion text (weak RAG side); ~31M transactions |
| Instacart / Dunnhumby | No text at all, so no RAG path |
| Northwind / Chinook / TPC-H | Teaching or synthetic benchmark databases; too clean, no real mess |

**Deciding factor:** Olist is the only candidate where a manager's question naturally needs both
paths, because reviews are tied to orders (e.g. "Do late deliveries cause bad reviews, and what do
those customers say?").

### Known risks and how they're handled

| Risk | Handling |
|---|---|
| Popular on Kaggle (for EDA/dashboards, not agent systems) | The dataset won't make the project stand out; the system will. Still a large step up from Superstore |
| Reviews are in Portuguese; many have a score but no comment (estimated ~40% with text, to be confirmed) | Decision D2 |
| Data covers 2016–2018 | Relative time ("last quarter") must resolve against the data's date range, not today: an ambiguity-handling design case |
| CC BY-NC-SA license | Raw data is **not** committed to the repo. Provide a download script and an attribution note |

### Defaults (assumed, can be changed)

- **Full dataset**, all 9 tables, no subsetting.
- **Natural mess only.** No artificially injected data issues in the product dataset. If controlled
  issues are ever needed for testing, they're clearly labelled as test-only.

### First step after locking

**Data profiling:** row counts, missing values, duplicates, join integrity, review text coverage and
language. Record the findings; the real data quality issues found drive the guardrail design.

---

## 12. Decision D2 — Portuguese review handling (locked)

**The problem:** Olist reviews are in Portuguese; the business manager asks questions and reads
answers in English. The decision is **when** translation to English happens.

### Options considered

| Option | How it works | Pros | Cons |
|---|---|---|---|
| **A — Translate at load time** | Translate every review to English once, during data loading. Store original + translation. Search over English | Simplest to build, explain and debug; English search models are strongest; data is readable for building and checking evals; answer quotes are already in English | One-time translation job (~40k short reviews, to be confirmed); translation can lose slang/nuance |
| **B — Search Portuguese directly** | Multilingual embeddings match English questions to Portuguese reviews; translate only the reviews used in an answer | No upfront job; keeps original wording; new reviews searchable immediately | Cross-language search usually weaker on short informal text; translation on every answer adds latency and cost; harder to build and check evals |

### Decision

- **Product uses Option A.** Reviews are translated during loading; the original Portuguese text is
  kept alongside the translation. Quotes shown to the manager are marked "translated from Portuguese".
- **Option B is built as a measured comparison — core scope, not a stretch goal.** Both approaches
  are run on the same review-question eval set and compared on retrieval quality, answer quality,
  latency and cost. The result becomes a decision record with evidence: the choice is made after
  testing, not assumed.
- **If the comparison shows B is better**, the decision is revisited, not defended.

### Production angle

In a real company new reviews arrive continuously. Option A becomes an **ingestion pipeline**
(new review → translate → store → index), not a one-off script. How far to take this (batch vs
incremental) is decided in the design phase.

### Deferred to design / profiling

- **Translation tool:** local open-source translation model vs LLM API (cost/time trade-off).
- **Exact review numbers** (how many have text, average length): from data profiling.
- **Embedding models** for A (English) and B (multilingual): part of D4.

---

## 13. Decision D3 — Database engine: PostgreSQL (locked)

**The question:** where the Olist data lives so the agent can query it. V2 loaded one CSV into
pandas; V3 has 9 related tables and needs a real database.

### Options considered

| | SQLite | DuckDB | PostgreSQL |
|---|---|---|---|
| What it is | Tiny file-based database | Embedded database built for analytics | Standard production database server |
| Setup | None | None | Runs in Docker |
| Analytics (joins, aggregations) | OK | Excellent | Good |
| Safety controls (read-only role, statement timeouts, permissions) | Basic | Basic | Built in |
| Can also store review vectors | No | Limited | Yes (pgvector) |
| Reads as | Toy | Local analytics / data science | Production |

### Decision: PostgreSQL

1. **Real-world shape.** In a real company an AI agent connects to a live database server; it does
   not load files.
2. **Safety enforced by the database, not only the code.** The agent connects as a **read-only role
   with statement timeouts**, so even a bad query cannot change data or run forever (defence in
   depth on top of the constrained tool layer).
3. **Possible single store for SQL and vectors** via pgvector. Decided in D4, not assumed here.

### Rejected alternatives

- **DuckDB** — excellent and simpler for analytics, but embedded in the app process: no database
  server, no roles/permissions, so the production safety story is lost.
- **SQLite** — too limited for safety controls and analytical workloads; reads as a toy.

### Implications

- Docker is required for local development (PostgreSQL runs in a container).
- Data loading becomes a proper ingestion step into PostgreSQL (ties in with the D2 translation
  pipeline).
- Read-only role and timeout configuration are part of the design phase.

---

## 14. Decision D4 — Vector store: pgvector; embedding model: chosen by test (locked)

Two parts: **where** review vectors are stored, and **which model** turns review text into vectors.

### Part 1 — Vector store: pgvector inside PostgreSQL

**Volume context (drives this decision):** Olist has ~100k orders and roughly ~40k reviews with
comment text (estimate, to be confirmed by profiling). Reviews are short. This is a **small vector
workload**, comfortably within what pgvector handles inside a normal PostgreSQL instance.

| | pgvector (inside PostgreSQL) | Separate vector DB (Qdrant, Chroma, Pinecone) |
|---|---|---|
| Systems to run | One | Two, kept in sync |
| Hybrid questions (numbers + reviews) | One SQL query can filter reviews by order data (e.g. reviews of *late* orders in *electronics*) | Fetch from both stores, combine in application code |
| Safety | Same read-only role and timeouts as D3 | Separate access setup |
| Scale fit | Easily handles ~40k reviews | Built for millions+ documents: capacity we don't need |
| Extras | PostgreSQL full-text search enables keyword + semantic hybrid search later | Varies |

**Why pgvector:**
1. **Hybrid questions are the core of V3**, and keeping vectors next to the order tables lets one
   query combine both. This is the main reason.
2. **Simplest solution that works.** At ~40k short reviews, a second database adds operational
   cost (another service, data sync, separate security) with no measurable benefit.
3. **One security boundary.** The read-only role and statement timeouts from D3 cover vector
   queries too.
4. **Portfolio breadth.** The SEC RAG project already uses ChromaDB; pgvector demonstrates a
   different, production-common approach.

**Rejected: a separate vector database.** Not justified at this volume.
**Revisit trigger:** if the review corpus grew to millions of documents, or vector search latency
or index size became a measured problem, a dedicated vector database would be reconsidered.

### Part 2 — Embedding model: chosen later, by test

Not chosen by opinion. D2 already requires two models:
- an **English** embedding model for translated reviews (Option A, the product), and
- a **multilingual** embedding model for direct Portuguese search (Option B, the comparison).

In the design phase, shortlist 2–3 free models per role and select based on results on the same
review-question eval set (retrieval quality, latency, size). The selection is recorded as part of
the D2 decision record.

---

## 15. Decision D5 — Routing: separate router step (locked)

**The question:** how the system decides what to do with each question. There are **five routes**:

| Route | Example |
|---|---|
| **SQL** (numbers) | "Revenue by state in 2017?" |
| **RAG** (reviews) | "What do customers complain about?" |
| **Hybrid** (both) | "Which categories have the most late deliveries, and what do those customers say?" |
| **Clarify** | "Who are our best customers?" |
| **Refuse** | "What's our marketing spend?" (data doesn't exist) |

### Options considered

| Option | How it works | Verdict |
|---|---|---|
| **A. Separate router step** | Classify the question into one of the 5 routes before planning; the planner then sees only that route's tools | ✅ **Chosen** |
| B. Planner decides implicitly | One planner sees all tools and routes while planning | Rejected as the default: routing is invisible and not separately measurable; larger planner prompt. Kept as the comparison (see below) |
| C. Keyword rules | e.g. "complain" → reviews | ❌ Rejected: brittle, real questions don't follow keywords |
| D. Free-roaming agent loop | LLM calls tools until it decides it's done | ❌ Rejected: unpredictable; contradicts the "planned, checked steps" principle |

### Why A

1. **Measurable.** Routing accuracy is success criterion S3; a separate step can be evaluated on its own.
2. **Smaller, focused planner.** V2 showed planner errors dominate; fewer tools in front of the
   planner means fewer chances to go wrong.
3. **Clarify and refuse happen early,** before spending time or cost on planning and queries.
4. **Hybrid stays one plan.** The SQL step's result feeds the review search (e.g. find worst
   categories → search reviews only for those). pgvector (D4) makes this a single-database operation.

### Router implementation: open

The router step is locked; **how it classifies** is decided in the design phase. Candidates:

- **LLM classification call** with structured output (route + reason) — default starting point.
- **Dedicated classifier model — Jev (TypeSafe, released Sep 2026)** (user suggestion). A "System
  One" model that doesn't generate text: given the input and a fixed set of options, it returns a
  choice with calibrated probabilities in ~70–500 ms; input-only pricing. Routing is a stated use
  case. Confidence scores could drive the Clarify route (low confidence → ask). Could be cheaper
  and faster than an LLM call.
- **Embedding-based classifier** (compare the question's embedding against labelled example questions).

Choose by the same rule as other decisions: measure on the routing eval set (accuracy, latency, cost).

### Comparison test: A vs B — documented, low priority

Run the separate router (A) against the single implicit planner (B) on the same question set to
confirm the router actually helps. **Low priority:** done after core V3 work, if time allows.
The decision does not depend on it, but the result strengthens the decision record either way.

---

## 16. Decision D6 — Querying 9 tables: semantic (business) layer (locked)

**The core tension:** V2's main principle is that the LLM never writes code; it only picks
predefined tools. With 9 related tables, answers need **joins**. How to keep the principle and
still answer real questions?

### Options considered

| Option | How it works | Verdict |
|---|---|---|
| A. Extend V2 pandas tools | Load tables into Python, add a "join" tool; the LLM chooses join keys | ❌ Rejected: doesn't use PostgreSQL; LLM-chosen join keys are a common source of silently wrong numbers |
| B. Text-to-SQL | The LLM writes SQL, with safety checks | ❌ Rejected as the product: breaks the core principle. **Kept as the core comparison baseline** |
| **C. Semantic (business) layer** | The LLM fills a structured request (metric, breakdown, filters, time period, sort/limit); the system compiles it into safe SQL. **Joins are predefined, never chosen by the LLM** | ✅ **Chosen** |

### How C works

The business vocabulary is defined once, in a config file:

- **Metrics** — e.g. "revenue" = sum of item prices on delivered orders; "late delivery rate" =
  share of orders delivered after the estimated date.
- **Dimensions** — e.g. state, product category, seller, month.
- **Relationships** — how the tables connect. Defined once, correct every time.

The LLM outputs only a structured request, e.g.
`metric: late_delivery_rate | by: product_category | year: 2017 | top: 5`,
which is compiled to SQL deterministically and run with the read-only role (D3).

### Why C

1. **Keeps the V2 principle.** The LLM never writes code; V2 → V3 is a natural evolution of
   "predefined tools".
2. **Joins are always correct** — defined by the builder, not guessed by the model.
3. **Messy data is handled in one place.** Cancelled orders, missing delivery dates, Portuguese
   category names etc. are dealt with inside metric/dimension definitions, so every answer treats
   them consistently. Profiling findings feed directly into these definitions.
4. **True pre-execution validation.** Requests are checked against the business layer *before* any
   query runs — an upgrade on V2's critic, which checks results after a tool runs.
5. **Industry pattern.** Enterprise analytics agents use semantic layers; it also plays directly to
   the builder's data-analysis background (defining metrics properly).

### Trade-off (accepted)

The agent can only answer what the business layer covers. Questions outside it go to the
**Refuse** route with an honest explanation. For a business manager who needs trustworthy answers,
coverage is traded for correctness. The text-to-SQL comparison measures exactly what that costs.

### Comparison test: semantic layer vs text-to-SQL — core scope

Both are run on the same structured-question eval set and compared on accuracy, failure
categories, coverage (how many questions each can answer), latency, cost, and safety. **Core scope**:
this is the main baseline from the original plan and the central "rejected alternative with
evidence" for V3. Reported honestly whatever the outcome (e.g. "text-to-SQL answers more questions
but is wrong more often / silently").

### Deferred to design

- Config format and exact metric/dimension definitions (informed by data profiling).
- How derived calculations and multi-step plans (e.g. SQL result → review search for hybrid
  questions) fit around the structured request.
- Whether to build the layer in-house or use an existing semantic-layer library.

---

## 17. Decision D7 — Eval design (locked)

**Goal:** prove each V3 claim with numbers a sceptical reviewer would trust.

### 1. What is measured — per component, then end to end

| Area | Question it answers | Criterion |
|---|---|---|
| Router | Right route chosen (SQL / RAG / hybrid / clarify / refuse)? | S3 |
| Structured path | Correct number? | S1 |
| Review retrieval | Right reviews found? | S2 |
| Review answer | Says only what the retrieved reviews say (faithfulness)? | S2 |
| Hybrid | Both parts correct and correctly combined? | S1, S2 |
| Clarify / refuse | Asks or refuses when it should — and not when it shouldn't? | S5, S6 |
| Messy-data traps | No silently wrong numbers from dirty data? | S4 |
| Safety | Malicious inputs fail (incl. prompt injection hidden in review text)? | Production |
| Cost and latency | Per question, per route | Production |

Every failure gets a **cause label** (router, business-layer request, retrieval, answer generation,
data quality, infrastructure, …), extending the V2 failure-cause table (S8).

### 2. Question set — ~150 questions

Sized for coverage: roughly the minimum per category to say something meaningful about each.

| Category | Approx. count |
|---|---|
| Structured (numbers), incl. ~15 messy-data traps | 45 |
| Review (RAG) | 25 |
| Hybrid | 20 |
| Clarify (ambiguous) | 15 |
| Refuse (unanswerable) | 15 |
| Multi-turn follow-ups | 15 |
| Safety / adversarial | 15 |
| **Total** | **~150** |

- **The builder writes the core set** using business-analyst domain knowledge. An LLM may draft
  extra candidates, but every question is human-reviewed. Expert-written questions are a
  credibility point.
- **Built incrementally:** each category's questions are written as that component is built
  (e.g. structured questions alongside the business layer), not all 150 up front.
- Counts are a target; adjust if a category proves too thin or too redundant.

### 3. Ground truth

- **Structured:** hand-written SQL per question, **independent of the business layer** (otherwise
  the system would be checked against itself).
- **Reviews:** relevant reviews labelled per question (for retrieval metrics). Answer faithfulness
  scored by an LLM judge; the builder spot-checks a sample to confirm the judge agrees with human
  judgment.
- **Clarify / refuse:** the expected route is the ground truth.

### 4. Guarding against fooling ourselves

- **Development / held-out test split** (roughly 60/40). Prompts and definitions are tuned on the
  dev set only; reported numbers come from the held-out set.
- **3 runs per question**; report mean and spread.
- **CI:** a small, fast subset runs on every change (regression gate); the full eval runs before
  releases, to control API cost.
- **Production feedback** (S10 / "improves from use"): real failures become new eval cases.

### 5. Comparisons

| Comparison | Priority | Decision |
|---|---|---|
| Semantic layer vs text-to-SQL | Core | D6 |
| Translate at load vs direct Portuguese search | Core | D2 |
| Separate router vs single implicit planner | Low | D5 |

### No direct V2 comparison

V2 only works on a single CSV and cannot query Olist; making it do so would mean building the
pandas-join option rejected in D6. So V2 is **not** run as a baseline. The V2 → V3 story is told
through findings instead: V2's failure-cause breakdown showed failures are semantic, not
structural; V3's semantic layer and pre-execution validation target exactly that. Text-to-SQL is
the real baseline.

---

## 18. V3 scope checklist — what a senior AI engineer is expected to show

The master checklist for V3. It consolidates the senior-AI-engineer gap check with the core/stretch
split. **Core** = must be done for V3 to count as complete. **Stretch** = only after all core items.
Details for each open item are filled into this file (or [v3-requirements.md](v3-requirements.md))
during the design phase — no new docs.

Status: ✅ covered · ⚠️ partial · ❌ not started

| # | Area | What it includes | Priority | Status | Where / notes |
|---|---|---|---|---|---|
| 1 | Problem statement, user, success criteria | Goal, business-manager user, question types, S1–S10 | Core | ✅ | §1–6 |
| 2 | Real, messy data | Olist, natural data quality issues, profiling | Core | ✅ (profiling pending) | D1, §11 |
| 3 | Design decisions with rejected alternatives | Every major choice records what was rejected and why | Core | ✅ | D1–D6, §11–16 |
| 4 | Evals | Per-component metrics, failure-cause labels, held-out set, 3 runs, CI subset, baselines | Core | ✅ (design) | D7, §17 |
| 5 | Non-functional requirements and capacity | Load, latency, cost, availability, rate limits, observability, verification plan | Core | ✅ (draft, needs review) | [v3-requirements.md](v3-requirements.md) |
| 6 | End-to-end architecture and request flow | Component diagram, data flow, step-by-step flow per route (SQL / RAG / hybrid / clarify / refuse) | Core | ❌ | Design phase |
| 7 | Guardrails as a layer | **Input:** off-topic, injection detection. **Output:** every number in the answer must come from the query result, review citations, personal-data redaction | Core | ⚠️ | Read-only role (D3) and pre-execution validation (D6) exist; rest in design |
| 8 | Prompt-injection / security threat model | Review text is untrusted input entering prompts; written threat model and defences (least privilege, structured outputs, content isolation) | Core | ⚠️ | Only an eval category so far (D7) |
| 9 | Service / API design | Endpoints, streaming responses, async, login, multi-user conversation state | Core | ❌ | Design phase |
| 10 | Failure handling | Timeouts, retries, fallback model/provider, provider abstraction, graceful degradation | Core | ⚠️ | Targets in NFRs (A1–A4), not yet designed. **Design idea (to explore in M0/M4):** ports-and-adapters LLM layer, like an ORM for models: pipeline code calls one owned interface (`llm.complete(job, ...)`), one adapter per vendor (Groq / Gemini / Claude / OpenAI, or LiteLLM behind it), vendor SDK imports only inside the adapters, per-job model config, fallback chain; the eval harness is the swap safety net because behaviour (not just syntax) differs across models. V2 has the coupling (4 modules call `Groq(...)` directly), which hid the deprecated-model 404 |
| 11 | Testing beyond evals | Unit, integration, end-to-end tests | Core | ❌ | Design phase |
| 12 | LLMOps | Prompt and model versioning; a model or prompt change must pass evals before release | Core | ❌ | Design phase |
| 13 | DevOps | Docker Compose, CI/CD, secrets management, environments | Core | ⚠️ | Docker required (D3); minimal deployment is core (D8) |
| 14 | "Why not multi-agent?" decision record | Reasoned explanation of why a single planned pipeline beats multi-agent here | Core (writing only) | ❌ | Add as a decision section |
| 15 | Showcase for recruiters | README, architecture diagram, demo video, eval dashboard/results, technical write-up, **business-impact framing** (e.g. "trusted answer in ~10s instead of waiting a day for an analyst") | Core | ❌ | End of V3 |
| 16 | Prioritisation | Core vs stretch scoping (this checklist) | Core | ✅ | This section |
| 17 | Data ingestion pipeline | Load Olist into PostgreSQL; reviews: translate → embed → index; daily incremental refresh (NFR D-1) | Core | ⚠️ | Mentioned in D2/D3; not yet designed |
| 18 | RAG retrieval quality | Hybrid keyword + semantic search (PostgreSQL full-text + pgvector), metadata filtering by order data, optional re-ranking | Core | ⚠️ | Store chosen (D4); retrieval design pending |
| 19 | Model and context strategy | LLM provider and models, which model for which step, context budget per prompt (schema / semantic-layer size), structured outputs | Core | ❌ | V3 tech stack not decided yet |
| 20 | Caching and cost optimisation | Result/semantic caching, model tiering, fewer LLM calls per route — designed and measured | Core | ⚠️ | Candidates listed in [v3-requirements.md](v3-requirements.md) §3 |
| 21 | Failure-diagnosis write-up | What broke, how it was found, what changed, before/after metrics (the "talk about the failure" signal) | Core (writing) | ❌ | Part of the showcase (#15) |
| 22 | User interface | Manager-facing chat UI calling the API (not running the agent directly): shows how each answer was computed (request, assumptions, review citations — S7), clarify flow, translated quotes marked, feedback buttons (#23). Likely an evolution of V2's Streamlit chat | Core | ❌ | Design phase |
| 23 | Feedback loop | Thumbs up/down → reviewed → new eval cases | Stretch | ⚠️ | Mentioned in §7 / D7 |
| 24 | Live quality monitoring and alerts | Sampled LLM-judge scoring on live traffic, alerts on degradation | Stretch | ❌ | Related to NFR O-3 |
| 25 | Role-based data access | e.g. regional manager sees only their region (PostgreSQL row-level security) | Stretch | ❌ | NFR S-5 |
| 26 | MCP server | Expose the agent's tools as an MCP server | Stretch | ❌ | Carried over from V2 plan |
| 27 | Router comparison test | Separate router vs single implicit planner | Stretch | ❌ | D5 (low priority) |
| 28 | Real-user contact | A few real users try the deployed system; failures logged and fed into evals (research-bar criterion 4) | Stretch | ❌ | Depends on deployment (#29) |
| 29 | Deployment | Minimal deployment of the service (Docker, hosted), tracing and latency tracking on it, load test against the NFRs. Hosting choice and cost: decided in design | Core | ❌ | D8. Moved from Deferred to Core |
| 33 | Agent loop with human approval | Decide plan-first vs bounded loop (step cap) by a comparison test; add a human-approval step with a real trigger in a read-only system | Core (decide in design) | ❌ | D9. Related to #10 and #30 |
| 30 | Large conversation state | Long chats and big state: context budget per prompt, trimming or summarising history, keep large query results out of the LLM context and out of the checkpoint (store references, not data), state size and retention limits | Core (decide in design) | ❌ | Related to #9 and #19. V2 starting point: questions-only sliding window of 3 plus full state in a SQLite checkpoint |
| 31 | Resumable / recoverable flows | Design to resume a failed or interrupted run: durable per-step state, idempotent steps, resume from the last good step instead of restarting, retry and dead-letter handling, user-visible run status | Core (decide in design) | ❌ | Related to #10 and NFR A1–A4. V2 starting point: LangGraph `SqliteSaver` checkpointing (crash/resume check: `dev_checks/check_checkpointer.py`) |
| 32 | Query-type and eval-metric coverage | Cover more query types than V2's 8 (add ambiguous, off-topic, "why", forecast / what-if, metadata questions) and add metrics beyond answer correctness: per-step tool and parameter accuracy, LLM-as-judge for fuzzy answers, refusal precision and recall, consistency over repeated runs (**pass^k**: succeeds on every one of k repeated attempts), injection resistance | Core (decide in design) | ❌ | Related to #4 and #7. V2 covered: aggregation, filtering, grouping and ranking, time-based, comparison, derived, compound and follow-up questions, plus a little unanswerable and adversarial; and scored answer correctness, refusal, multi-turn, consistency, number faithfulness, cost, latency and a small safety test. Reference evals to check (names and metrics to verify): Ragas agent metrics, DeepEval, LangSmith trajectory evals, tau-bench, Spider / BIRD |

**Deliberately excluded:** bias/ethics review (low relevance for business analytics on anonymized
data), fine-tuning (semantic layer + evals is the stronger story), multi-agent (covered as a
"why not" decision record, #14).

---

## 19. Milestones (build order)

Each milestone ends with something working and demo-able. Details are planned when each milestone
starts. Numbers in brackets are §18 checklist rows.

1. **M0 — Foundation:** data loaded into PostgreSQL, data profiling, model/stack choice (#2, #17, #19, #13).
2. **M1 — First working version:** numbers questions end to end — semantic layer, API, UI, tracing, first evals (#6, #9, #22, #4).
3. **M2 — Reviews:** translate → embed → index, review search, translation comparison (#17, #18).
4. **M3 — Routing:** router, hybrid questions, clarify and refuse.
5. **M4 — Hardening:** guardrails, prompt-injection defences, failure handling, caching, tests, LLMOps (#7, #8, #10, #11, #12, #20, #14).
6. **M5 — Proof:** full held-out eval, text-to-SQL baseline, load test against NFRs (#4, #5).
7. **M6 — Showcase:** README, diagram, demo video, write-ups (#15, #21).

Minimal deployment (#29) and the agent-loop decision (#33, D9) are core. Their milestone placement is decided when milestones are planned. Then stretch items (#23–#28).

---

## 20. What the plan can't guarantee (read before building)

The scope clears the research bar on paper; the outcome depends on these:

1. **Execution quality decides it.** Finish M0–M6 properly before any stretch item. A smaller
   system done well beats a large one half-done.
2. **The first impression is the README, not the code.** Recruiters spend ~30 seconds there. M6
   (showcase) is where the impression is made — not optional polish.
3. **The interview tests the builder, not the repo.** Every decision and trade-off must be
   explainable in your own words; the decision sections (§11–17) are the preparation material.
4. **V2 polish comes first.** Same repo: if V2's eval files are missing, the impression suffers
   before V3 is seen.
5. **Report results honestly**, including unflattering ones. Honest trade-offs are a stronger
   signal than perfect-looking numbers.
