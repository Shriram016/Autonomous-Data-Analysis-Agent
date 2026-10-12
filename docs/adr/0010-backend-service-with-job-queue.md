# The agent runs as a backend service with a job queue; the UI is a client

A backend API (e.g. FastAPI) handles login, quotas, rate limits and tracing, and puts each question on a durable job queue; separate worker processes run the agent and stream progress back through the API to the UI. The UI only sends questions and shows streamed progress.

## Why

1. **Approval pauses.** The bounded loop can stop and wait for the manager to confirm an action, possibly for minutes. A queued job with saved state can wait and resume; a held-open web request cannot.
2. **Durability.** If the API restarts mid-question, the job is still on the queue and a worker picks it up; nothing is silently lost.
3. **Spike handling.** The queue absorbs the 200-user spike; workers scale independently of the API.
4. **One place for cross-cutting rules.** Login, per-manager quotas, global concurrency limit, central provider rate limits and tracing live in the backend, not tangled into UI code; other clients (Slack bot, MCP) can be added later.
5. **Learning goal (secondary, honest).** At ~1.7 questions/s an in-process queue would likely suffice; the job queue is also chosen so the builder learns to design and run queue-based backends for loads beyond this scenario.

## Considered Options

- **Agent inside the UI (V2 Streamlit).** Simplest, but cannot serve 100 concurrent users, and login/quotas get tangled into UI code. Rejected.
- **Backend service without a job queue** (in-process concurrency limit + waiting queue). Meets the load numbers with fewer moving parts, but loses durability across restarts and handles approval pauses poorly. Rejected.

## Consequences

- Extra pieces to run: a queue (e.g. Redis) and worker processes, in local Docker Compose and in deployment.
- Progress streaming goes worker → API → UI (e.g. via pub/sub), which must still meet the < 1s first-feedback target.
- Jobs must be safe to retry (no duplicate actions) and carry a status the manager can see.
- Open for design: queue technology, streaming protocol, worker count.

## Questions that drove this

- How many users at once, and what happens at the spike?
- What happens to an in-progress question if a process restarts?
- Where does the agent wait while a human approves something?
- Is this the simplest thing that works, and if not, what justifies the extra parts?
