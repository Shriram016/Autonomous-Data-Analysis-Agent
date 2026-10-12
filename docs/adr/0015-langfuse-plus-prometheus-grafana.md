# Langfuse for LLM traces; Prometheus + Grafana for system metrics; OpenTelemetry underneath

**Langfuse** (Langfuse Cloud — changed from self-hosted on 2026-10-12, see Consequences) records each question's trace: route, steps, retrieved reviews, every LLM call with prompt, tokens, cost and time; it also holds prompt versions. **Prometheus** collects system metrics (request rate, p50/p95 per route, error rate, queue length, worker health); **Grafana** turns them into the dashboard and fires alerts. Both are fed through **OpenTelemetry**, the vendor-neutral standard for emitting traces and metrics, so either backend can be swapped later.

LLM-tracing tools don't cover queue length, worker health or p95 alerting well, and system-metrics tools don't understand prompts and tokens; each half uses the tool built for it.

## Considered Options

- **LangSmith.** Deep LangGraph integration, but self-hosting is paid/enterprise and it ties us to LangChain. Rejected.
- **Arize Phoenix.** Open-source and strong for eval analysis; Langfuse chosen for prompt management and V2 familiarity.
- **Langfuse alone.** Misses system-level metrics and alerting. Rejected.

## Consequences

- **Langfuse runs as Langfuse Cloud, not self-hosted (2026-10-12).** Self-hosted Langfuse needs its own database, ClickHouse and file storage (~3–4 GB RAM), which would push the single VM to ~16 GB (~$100+/month). Cloud is the same product, so code doesn't change; traces leave our system but are already masked (ADR 0019); free-tier limits to be checked at setup.
- **Prometheus + Grafana also run as Grafana Cloud (2026-10-12)** — hosted Prometheus-style metrics, dashboards and alerts on its free tier; an OpenTelemetry collector / agent on our server pushes metrics there. Metrics carry no personal data. Free-tier limits to be checked at setup.
- Net effect: no observability services on our VM; it runs only our app, data and Keycloak (~6 GB → 8 GB instance).
- Code instruments once via OpenTelemetry; dashboards and alert rules become versioned config.
- Langfuse prompt versions connect to the "prompt change must pass evals" release rule.

## Questions that drove this

- What must be visible: LLM behaviour, system health, or both? Does one tool cover both well?
- Can we self-host without paying or locking in?
- If we change tools later, how much code changes?
