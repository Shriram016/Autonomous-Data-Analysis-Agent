# V3 Non-Functional Requirements (NFRs)

**Status:** Draft. All numbers are **proposed targets**, to be reviewed before the V3 design phase.
**Related:** [v3-problem-statement.md](v3-problem-statement.md) — defines *what* V3 does (functional
requirements and decisions D1–D8). This file defines *how well* it must do it.

> **Rule for V3:** these requirements must be considered **before** designing and building V3, the
> same way a production system is specified before it's built. Every design choice should trace
> back to a requirement here, and every target should be **verified** (load test, eval, or
> monitoring), not just stated.

---

## 1. Scenario (gives the numbers a story)

**Olist's internal analytics assistant.** Business managers across the company use it to ask
questions about orders, deliveries, sellers and customer reviews.

| Assumption | Value (proposed) |
|---|---|
| Total registered users | 500 managers |
| Normal concurrent active users | ~20 |
| Peak concurrent active users (business hours, e.g. Monday morning reporting) | ~100 |
| Max design load (spike) | 200 concurrent (2× peak) |
| Questions per active user during peak | ~1 per minute |
| Questions per user per working day (average) | ~5 |

---

## 2. Requirements

### 2.1 Load and throughput

| ID | Requirement | Target (proposed) |
|---|---|---|
| L1 | Sustained peak throughput | ~100 concurrent users → **~1.7 questions/sec** |
| L2 | Spike handling | 200 concurrent users without crashing: excess requests queued or politely rejected |
| L3 | Behaviour beyond max load | Graceful degradation (queue, "busy, try again"), never wrong answers or crashes |

### 2.2 Latency (end-to-end, per route)

| ID | Route | p50 | p95 |
|---|---|---|---|
| T1 | Clarify / Refuse | < 2s | < 4s |
| T2 | SQL (numbers) | < 5s | < 10s |
| T3 | RAG (reviews) | < 6s | < 12s |
| T4 | Hybrid | < 10s | < 20s |
| T5 | Time to first feedback (status/progress shown to user) | < 1s | < 2s |

### 2.3 Cost

| ID | Requirement | Target (proposed) |
|---|---|---|
| C1 | Average cost per question | Tracked per route; target set after first measurements |
| C2 | Monthly budget for the scenario | Estimated from C1 × ~55k questions/month (500 users × 5/day × 22 days) |
| C3 | Cost visibility | Cost per question recorded and shown on a dashboard |

### 2.4 Availability and resilience

| ID | Requirement | Target (proposed) |
|---|---|---|
| A1 | Availability during business hours | 99.5% (measured during load tests / demo period) |
| A2 | LLM provider outage or rate-limit | Fallback (alternate model/provider) or a clear error message, **never a fabricated answer** |
| A3 | Database outage | Clear error; no partial or stale answers presented as fresh |
| A4 | Timeouts | Every external call (LLM, DB, embedding) has a timeout; per-question overall time cap |

### 2.5 Data

| ID | Requirement | Target (proposed) |
|---|---|---|
| D-1 | Review freshness | New reviews translated, embedded and searchable within **24 hours** (daily ingestion) |
| D-2 | Data growth | Still meets latency targets at **10× current data volume** |
| D-3 | Data correctness | Data quality rules (from profiling) applied consistently via the semantic layer |

### 2.6 Security and privacy

| ID | Requirement |
|---|---|
| S-1 | Users must log in; every request is tied to a user |
| S-2 | Agent uses a **read-only** database role with statement timeouts (D3) |
| S-3 | No personal data (customer IDs, zip codes, etc.) exposed in answers or logs beyond what's necessary |
| S-4 | Prompt-injection resistance, including instructions hidden inside review text |
| S-5 | *Candidate:* role-based data access (e.g. a regional manager sees only their region) via PostgreSQL row-level security |

### 2.7 Rate limiting and quotas

| ID | Requirement | Target (proposed) |
|---|---|---|
| R-1 | Per-user quota | e.g. 30 questions/hour |
| R-2 | Global concurrency limit | Protects LLM provider limits and the database |
| R-3 | Stay within LLM provider rate limits | Enforced centrally, not by luck |

### 2.8 Observability (service-level objectives)

| ID | Requirement |
|---|---|
| O-1 | Every request traced end-to-end: route, steps, retrieval, LLM calls, cost, latency, outcome |
| O-2 | Dashboard for latency (p50/p95), error rate, cost, route mix, cache hit rate |
| O-3 | Alert-worthy conditions defined (e.g. p95 above target, error rate above threshold) |

---

## 3. Rough capacity estimate (back-of-envelope)

| Quantity | Estimate |
|---|---|
| Peak questions/sec | 100 users × 1/min ≈ **1.7 q/s** |
| LLM calls per question | ~3–4 (router, planner, answer, occasional fix/retry) |
| Peak LLM calls/sec | ≈ **5–7 calls/s** (≈ 300–400 calls/min) |
| Monthly questions | ≈ **55k** |

**Reality check — the LLM provider is the real bottleneck, not the database.** Free-tier rate
limits (see [others/groq-model-details.md](others/groq-model-details.md)) are likely far below
~300–400 calls/min. This is not a blocker; it's a **design driver**. Candidate responses (decided
in the design phase):

- **Caching** — the data is mostly static, so repeated or similar questions can reuse results.
- **Cheaper, faster models for simple steps** — e.g. a classifier for routing (Jev, D5) instead of an LLM call.
- **Queueing and backpressure** — absorb spikes instead of failing.
- **Fewer LLM calls per question** — e.g. skip steps for Clarify/Refuse routes.
- **Honest documentation** of the gap: "requirement X, provider limit Y, design choices Z,
  measured result W."

---

## 4. Verification plan

| Requirement area | How it's verified |
|---|---|
| Load, throughput, latency (L, T) | Load test (e.g. Locust or k6) with a realistic question mix; report p50/p95 per route at normal, peak and spike load |
| Cost (C) | Measured per question during eval and load tests |
| Resilience (A) | Fault-injection tests: simulate LLM timeouts, rate-limit errors, DB unavailability |
| Data (D) | Ingestion run timing; latency re-test at 10× data volume (synthetic scale-up for testing only) |
| Security (S) | Safety/adversarial eval questions (D7); permission tests for the read-only role |
| Rate limiting (R) | Load test beyond quota/concurrency limits; confirm graceful rejection |
| Observability (O) | Dashboard screenshots and traces in the write-up |

---

## 5. Open questions (before design)

1. **Scenario size:** keep 500 users / ~100 peak, or adjust?
2. **Latency targets:** are the per-route p50/p95 targets reasonable for a business manager?
3. **Cost target:** set a number now (e.g. < $0.01 per question), or after first measurements?
4. **Role-based access (S-5):** core scope or stretch?
5. **Load-test environment:** local machine vs deployed environment (ties to deferred D8).
