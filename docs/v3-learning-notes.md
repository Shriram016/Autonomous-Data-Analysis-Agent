# V3 learning notes

Plain-language explanations of concepts that came up while building V3, plus questions to learn
later. Interview-style system-design questions live in [v3-cross-examination.md](v3-cross-examination.md).

## Learn later

- Rate limiter internals (token bucket) — from failure-handling design
- Connection pools and PgBouncer — from database failure design
- Atomic publish and data versioning — from daily-publish design
- **Database sync between a primary ("master") and its copies ("replicas", "child DBs")** —
  raised 2026-10-19 (see Q3 in [v3-cross-examination.md](v3-cross-examination.md)):
  - How does a primary send its changes to the replicas? (physical vs logical replication, WAL streaming)
  - What decides whether a record is inserted, updated or deleted in the copy?
  - How does a copy learn about deletes and updates, not only new rows? (CDC vs watermark loads, tombstones)
  - Synchronous vs asynchronous replication: what is replication lag, and what can be lost on failover?
  - How does CDC work (for example Debezium → Kafka → warehouse)?
- **Celery workers, end to end** — raised 2026-10-23 (M1.4): revisit what we coded
  (`worker/celery_app.py` settings, `tasks.py`, `jobs.py`) and the wider options:
  - The job life cycle: queued → `STARTED` → `SUCCESS` / `FAILURE` → result expires; why an
    unknown or expired job also shows as `PENDING`
  - Crash safety: `acks_late`, `task_reject_on_worker_lost`, the Redis visibility timeout, and
    "at least once" delivery (a job can run twice, so tasks should be safe to repeat)
  - Worker pools (prefork, threads, solo), concurrency, prefetch, soft vs hard time limits
  - Retries with backoff, task routing to separate queues, rate limits, periodic tasks (beat)
  - Monitoring (Flower), and how Dramatiq / RQ / arq solve the same problems
- **Docker deployment and CI/CD pipelines** — raised 2026-10-24 (M1.5); part of the plan
  (M6–M7), to study properly at the end of the build:
  - Images vs containers, layers and caching, image registries, tags per git commit
  - Compose locally vs production hosting (one VM, ECS, Kubernetes); health checks, restarts
  - A GitHub Actions pipeline: tests → build → push → migrate once → roll out → roll back
  - Secrets in production (a secret manager instead of `.env`), and zero-downtime deploys
- **Alembic and migrations in a deployment pipeline** — raised 2026-10-24 (M1.5):
  - What a migration is (`upgrade()` / `downgrade()`), the `alembic_version` table, autogenerate
    and why a person must still check the drafted file
  - Where `alembic upgrade head` runs: a one-off `migrate` container locally; in production one
    pipeline step (GitHub Actions → EC2: build → push → migrate once → start API + workers),
    never inside the API's start-up (several copies would race)
  - Safe changes with old and new code running side by side (expand → migrate → contract),
    and Kubernetes / ECS one-off jobs for the same step
- **Databases in production: Docker or managed, set-up and best practice** — raised
  2026-10-29 (M3, while creating `business.review_vectors`):
  - Is the database run in Docker in production, or as a managed service (AWS RDS / Aurora,
    Cloud SQL, Supabase, Neon)? Why most teams run the database outside containers
  - Where a table is really stored: the data directory on disk, Docker volumes (our
    `pgdata`), what is lost when a container or a volume is removed
  - How a new table reaches production: a migration in the deploy pipeline, never by hand
  - Best practice: backups and point-in-time restore, replicas, one role per job (least
    privilege, as with `adaa_query` / `adaa_review_writer`), secrets in a secret manager,
    no public network access, monitoring (slow queries, disk, connections), upgrades,
    pgvector as an extension on a managed host
- **Batch API calls to an LLM (Claude and others)** — raised 2026-10-29 (M3, before the
  full run of 42,562 reviews with `review_batch.py`):
  - Normal call vs batch: a normal call answers in seconds and you wait for it; a batch takes
    many requests at once, answers in the background (most in < 1 h, at most 24 h) at half
    the price. When each one fits: a user waiting (normal) vs work nobody waits on (batch)
  - How it works: create → poll the status → download the results (kept 29 days at
    Anthropic) → match each answer by its `custom_id`. Limits (100,000 requests or 256 MB per
    batch), the result types (succeeded / errored / canceled / expired)
  - The same idea at other providers: OpenAI Batch API (a JSONL file upload), Google Gemini
    batch mode, AWS Bedrock batch inference. What differs between them
  - Prompt caching inside a batch (best effort), and why it matters less for a short prompt
  - In production: idempotent writes (upsert), save the request map before the send and the
    raw answers at the first download (never pay twice), resend only the failed requests,
    one batch at a time, a timer job (Celery beat / cron) that polls and collects, alerts
    when a batch expires or fails, cost tracking per batch, splitting very large jobs
- **Fingerprints (SHA-256)** — raised 2026-10-22 (M1.3): what a hash is, why any one-character
  edit changes it, why each answer records version + fingerprint (semantic layer, prompts)

---

## Local setup tips (problems already hit)

- **Docker Desktop must run** for Postgres / Redis, DBeaver, integration tests and check scripts.
  Turn on Settings → General → "Start Docker Desktop when you sign in". The containers then
  start by themselves (`restart: unless-stopped`).
- **Start the services by hand** (repo root):
  `docker compose -f infra/docker-compose.yml --env-file .env up -d`
- **`uv` not found in a terminal:** the terminal started before uv was installed. Restart VS
  Code (uv lives in `C:\Users\<you>\.local\bin`).
- **VS Code "file changed on disk":** click **Revert**, not Overwrite. Saving an old open copy
  once undid three fixes in `profile_olist.py`; the pre-commit hook caught it.
- **DBeaver connection:** host `127.0.0.1`, port `5433`, database `adaa`, user `adaa_loader` or
  `adaa_query`, password from `.env`.
- **What runs on commit / push:** commit → ruff, ruff format, mypy (staged Python only); push →
  unit tests. Integration tests, check scripts and evals run by hand.

---

## M0.1 — Skeleton

### Pre-commit hook: what runs, how, and what it checks

**What:** git can run a script automatically before a commit is saved. If the script fails, the
commit is blocked.

**How it runs:**

```
once:        uv run pre-commit install   → writes .git/hooks/pre-commit
every time:  git commit → hook reads .pre-commit-config.yaml → runs the hooks on the
             Python files being committed → pass: commit saved / fail: commit blocked
```

Unstaged changes are stashed (hidden) during the check and restored after, so only what is being
committed gets checked.

**Our two hooks** (rules in `backend/pyproject.toml`):

| Hook | Job | Catches / fixes |
|---|---|---|
| `ruff check --fix` (linter) | Likely mistakes and bad patterns | Unused imports, undefined names, import order, common bug patterns (e.g. `def f(x=[])`), outdated syntax, needlessly complex code; fixes what is safe, reports the rest |
| `ruff format` (formatter) | Consistent layout | Spacing, quotes, line breaks, line length 100 |

**Layering (locked):** faster checks run more often.

| Layer | When | Runs |
|---|---|---|
| pre-commit | every `git commit` | ruff lint + format, mypy |
| pre-push | every `git push` | unit tests |
| CI | every push, on GitHub | everything, incl. integration tests (need Docker) |
| manual | with approval | real-LLM dev_checks, evals (cost money) |

Why not all tests on commit: slow commits make people skip hooks (`--no-verify`); integration
tests fail whenever Docker is off; CI is the real safety net because it can't be skipped.

---

## M0.2 — Docker services

### Image, container, compose, volume

| Term | Plain meaning |
|---|---|
| **Image** | A packaged, read-only recipe for a program (e.g. `pgvector/pgvector:pg17` = Postgres 17 with pgvector) |
| **Container** | A running copy of an image. Removing it deletes the container, not your data, if data is on a volume |
| **Docker Compose** | One YAML file describing several containers that run together (`infra/docker-compose.yml`) |
| **Volume** | Storage that lives outside the container. Proven in M0.2: data survived `down` (containers removed) and `up` |
| **Health check** | A command Docker runs repeatedly (`pg_isready`, `redis-cli ping`) to know a service is truly ready, not just started |
| **Port mapping** | `127.0.0.1:5433:5432` = your machine's port 5433 → the container's 5432, reachable only from this machine |

### Two real problems hit in M0.2 (good interview stories)

1. **Port already taken.** A Postgres installed directly on Windows already listened on 5432,
   so Docker couldn't bind it. Fix: map the container to 5433 instead of touching the other
   install. Lesson: check what owns a port (`Get-NetTCPConnection -LocalPort 5432`).
2. **Connections hung forever.** `localhost` can resolve to IPv6 `::1` first on Windows, while
   Docker listened only on IPv4 `127.0.0.1`, and the connection attempt waited with no limit.
   Fix: use `127.0.0.1` explicitly **and** a 2 s connect timeout. Lesson: every network call
   needs a timeout — exactly the "never hang" rule from the failure design.

### Database schema (Postgres)

A schema is a named folder inside one database that groups tables: `business` (Olist data),
`agent` (flags, tasks), `conversation` (turns, checkpoints), `staging` (daily loads). Permissions
can be granted per schema, which is how the read-only role will be enforced.

### Database roles (least privilege)

A role is a Postgres login with its own permissions, granted per schema, table or even column;
anything not granted is refused by Postgres itself. Like office badges: each opens only certain
doors. Named after the job that holds the badge:

| Role | Access | Used by |
|---|---|---|
| `adaa_owner` | everything | setup / migrations only |
| `adaa_loader` | write `staging`, publish to `business` | load + daily ingestion |
| `adaa_query` | read `business` only | agent queries + review search |
| `adaa_actions` | write `agent` only | flags, tasks, escalations, preferences |
| `adaa_memory` | read/write `conversation` only | turns, checkpoints |

Why: if the agent is tricked or buggy, its badge physically can't change data — stronger than
"our code promises not to".

### Container crash: is the data lost?

No, if the change was committed. The container is the Postgres program; the data is in the volume
`adaa_pgdata` on disk. Postgres writes each change to the write-ahead log (WAL) before it
confirms `COMMIT`, and replays the WAL after a crash. Data is lost only when the transaction did
not commit, the volume is deleted, or the disk fails without a backup.

`restart: unless-stopped` (added 2026-10-19) starts both containers again after a crash or a
Docker Desktop restart. They stay down only if you stop them yourself. DBeaver can connect only
while the container runs.

Production comparison (replicas, failover, point-in-time recovery): see Q2 in
[v3-cross-examination.md](v3-cross-examination.md).

### Redis AOF

Append-only file: Redis writes every change to disk, so queued jobs survive a restart instead of
vanishing (locked in the failure design).

---

## M0.4 — Load into Postgres

### "Faithful but typed"

The tables keep the same rows and column names as the CSV files. Each column gets the correct
type. The load fixes nothing and removes nothing. The semantic layer applies business rules.

| Data | Type | Reason |
|---|---|---|
| IDs | text | An ID is a label, not a number |
| Dates | timestamp | Date calculations work directly |
| Money | numeric(10,2) | Exact; a float type can store 0.1 as 0.1000000001 |
| Zip prefixes | text | Leading zeros: `01310` as a number becomes `1310` (23,995 customers affected) |
| Empty cells | NULL | Empty means unknown |

### Primary key vs foreign key

- **Primary key:** a column (or columns) whose values are unique in a table, for example
  `orders.order_id`. Postgres refuses a duplicate. We added one only where the data is unique.
  `reviews.review_id` repeats, so it has no primary key.
- **Foreign key:** a rule that a value must exist in another table. We added none, because the
  real data has orphans (for example, categories missing from the translation table). A foreign
  key would refuse real rows and break "faithful".

### COPY

`COPY` is the Postgres bulk-load command. It streams a whole file in one operation.
1.55 million rows took 4.4 seconds. Row-by-row `INSERT` would take minutes.

### Transaction and atomic swap

A transaction groups statements: all succeed, or none take effect. The publish step drops the old
`business` tables and moves the new ones from `staging` in one transaction. A reader sees all old
data or all new data, never a mix. If the row counts do not match `manifest.json`, the load stops
before the publish, and `business` does not change (an integration test proves this).

---

## M0.6 — Semantic layer draft

### Grain and double counting (fan-out)

Grain = what one row describes. `order_items`: one item. `payments`: one payment for a whole
order. `reviews`: one review of an order. A number about the whole order cannot be split by
something about single items: one payment of 120 for an order with a toy and a book would count
120 for toys and 120 for books (240 in total). This error is called double counting, or fan-out.

The grain tree: `order` is the parent of `item`, `payment` and `review`. A metric can use a
dimension at its own grain or at `order`. Each metric and dimension has a `grain` label, and one
check in code applies the rule, so no one has to remember special cases.

### Why revenue = item price (D1)

Item price + freight = payment value for 99.7% of orders. The total payment is 0.17M higher, but
98% of that gap comes from 775 orders with a payment and no items (unavailable / canceled), and
only 2% from interest and vouchers. With delivered orders only (D2): revenue 13.22M + freight
2.20M = 15.42M ≈ total paid 15.42M. Payment value can't split by category or seller, so revenue
uses item price, and freight / total paid are separate metrics.

### The YAML `on` trap

YAML 1.1 (used by PyYAML) reads a bare `on`, `off`, `yes` or `no` as true / false. A join key
written `on:` loaded as the boolean `True`, and the loader reported the field as missing. Fix:
name the key `condition`. Lesson: avoid these words as keys, or quote them.

### Semantic layer fingerprint

The loader computes a SHA-256 of the 4 YAML files. Each answer can record it, so we can always
prove which definitions produced a number (gap G6, semantic-layer versioning).

---

## M1.1 — Query compiler

### The path of a numbers question

```
English question → LLM fills the form (M1.3) → compiler → SQL → Postgres (adaa_query) → rows + "how"
```

M1.1 built everything after the form. The compiler does not understand English; it only reads
the form. Building and testing this part first means a wrong number later can only come from a
wrong form, which we can see directly.

### The structured request (the form)

Fields: `metric`, up to 2 `dimensions`, `filters` (dimension, op, values), `period`, `sort`,
`limit` (at most 1,000). The form refuses unknown fields, so the LLM cannot add `"sql": ...`.
The same Pydantic model becomes the LLM's output schema in M1.3: one definition, two users.

### How the compiler finds the joins by itself

The form never names tables. Every definition in the YAML contains table names in its SQL
(`sum(order_items.price)`, `customers.customer_state`, the delivered filter on `orders`). The
compiler collects them, starts at the metric's table, and follows `joins.yaml` (shortest path,
many-to-one only). One needed table = no join. Example: `review_count` with no period uses only
`reviews`; with a period it also joins `orders`, because the period is on the order date.

### Placeholders and SQL injection

Values never go into the SQL text. The SQL has `%(f0_0)s`, and the value travels separately;
Postgres always treats it as data. A value like `SP'; DROP TABLE orders; --` stays a value.
A unit test proves it.

### Why the runner always uses adaa_query

Answering a question only reads. The SQL comes from the LLM's form, so the runner is fixed to the
read-only role with a 5 s limit: if anything upstream goes wrong, Postgres itself refuses any
write. Writes happen elsewhere, with their own roles: memory (`adaa_memory`), approved actions
(`adaa_actions`, `agent` tables only), loading (`adaa_loader`). No path changes business data
from a question.

### Setup vs normal use (roles)

`roles.py` runs once at setup (or when a role or password changes). It tells Postgres that a
user exists, its password and its permissions. `settings.py` + `.env` only tell our code how to
log in. Both sides must match; "create or update" keeps them matched, and running it twice is
safe (idempotent). Default privileges give every new table from the daily load read permission
for `adaa_query` automatically; a real reload proved it.

### D3: no period = all available data

The first default (2017-01 to 2018-08) quietly lowered totals (13,181,027 instead of
13,221,498). "Total revenue" means everything, so no period now means all data, and thin months
(< 500 orders) are flagged in month / year answers instead. Changing a default's meaning raised
the semantic layer to v0.2.0, and the fingerprint changed: every answer records which
definitions produced it.

### A pattern worth a hybrid question later

The late-delivery rate jumped to 14.1% in Feb 2018 and 19.0% in Mar 2018, against ~5% in other
months. "Why were deliveries late in March 2018, and what did customers say?" is a natural
hybrid question for M3.

---

**Why one ruff version:** the hook calls the project's own ruff via `uv run`, pinned in
`uv.lock`, so the hook, the editor and CI never disagree.

## M1.2 — `llm.complete`

### Why the logs go to the console, not to a file

The console (stdout) is the pipe, not the storage. In deployment the container runtime catches
stdout, a log agent (Grafana Alloy, Fluent Bit, CloudWatch agent) ships each line within seconds
to a central store (Grafana Loki, CloudWatch, Elasticsearch), and the store keeps it after the
container is gone. A file inside the container dies with the container too, gives one file per
replica, and needs rotation. Rule name: Twelve-Factor App, "logs are a stream of events".
Data we must keep (tokens and cost per question) goes to the **database**, not to logs.

### Thinking tokens

Thinking tokens are billed at the output price and are **inside** `output_tokens`, not added on
top. `thinking_tokens` is stored only to show how much of the output was thinking.

### Identity federation vs API key

Federation: a cloud or CI platform proves who the app is and gets a token that expires in
minutes, so no permanent key exists. It needs an identity provider (AWS, GCP, Azure, GitHub
Actions); a laptop has none, so local work uses an API key. Revisit at deployment and in CI.

### The path of one LLM call

```
complete("agent", messages, StructuredRequest)          llm/complete.py
  → job settings from config/llm.yaml                    llm/config.py
  → JSON schema made from the form class
  → adapter.send(messages, schema, job)                  adapters/anthropic_adapter.py
       (system prompt split out, schema cleaned, thinking from config) → Claude
  → Pydantic checks the reply; one retry with the errors if it fails
  → one usage log line → LlmResult(output=form, usage, attempts, model, seconds)
```

Nothing calls this with a real question yet: M1.3 (the agent) joins it to the M1.1 numbers
path. The **fake adapter** stays: it makes the `complete()` tests free, fast, repeatable, and
able to create failures on purpose (bad JSON, outage) that a real model cannot.

### Why check the reply if strict mode forces the shape

Strict mode guarantees valid JSON in the schema's shape. But strict mode does not accept some
rules (`minLength`, `maxItems`, `minimum`…), so the adapter removes them from the copy it sends,
and the form's own validators can't be expressed in a schema at all. Pydantic checks every rule
on the reply. One definition (the form class) gives both the schema and the check.

### First real run (2026-10-21)

3 questions, all correct on attempt 1. ~1,560 input tokens per question (prompt + schema),
25–67 output, ~$0.00018 per question, 1.8 s per call. The first call took 3.5 s: a new schema
is compiled once and cached for 24 hours. 1–3 s per LLM call is normal (network, reading the
prompt, writing tokens one by one); see Q5 in the cross-examination doc.

## M1.3 — Agent

### Value linking: the model knows names, not values

The prompt listed `product_category` but not its values, so the model could write "toy" for
`toys`; the query runs, matches nothing, and returns an empty answer that looks correct. Fix in
two layers: the real values of each small dimension go in the prompt (read through the normal
compiler, so only values a query can match), and code checks every filter value after the form
(close match → replaced and noted; unknown → plain message). State codes got names
(`PA` = Pará, not Paris), and the model is told to copy an unknown place as written, never to
guess a code.

### D2 was a default in the design but a fixed rule in the code

The YAML wrote `order_status = 'delivered'` into each metric's own filters, so "canceled
orders" became `delivered AND canceled` = 0 — a wrong answer that looks right. D2 always said
"override via the status dimension or a filter". v0.3.0 makes it a default the compiler adds
only when the form names no status; the two delivery metrics keep it built in and refuse a
status. Lesson: a design rule is only real when a test proves the code follows it
(`test_canceled_orders_are_not_zero`: 461, not 0).

### The agent graph (step 6)

```
start → understand → query → answer → finished answer
            │          │
            └─ error ──┴──→ stop with a plain message
```

`understand`: agent prompt + question → form → value check. `query`: compiler → SQL → rows as
`adaa_query`. `answer`: code formats the numbers, the LLM writes 1–3 sentences, the number
guardrail checks them; any failure gives the template answer (no retry). The context (semantic
layer, catalogue, data date, prompts) is loaded once per worker process; each process keeps
its own copy. The state is a Pydantic model, so a future checkpoint is checked when it is
loaded. Diagram: https://claude.ai/artifact/GnnQeAyqyQF14sbu34TpYY.

### API, queue and workers (restaurant picture)

The API endpoint is the waiter: it takes the question at once and gives back an order number.
The Redis queue is the order slips. The workers are the cooks: each takes one slip and runs the
graph (3–8 s). With 20 users and 4 workers, 4 questions run at a time and the rest wait a few
seconds; the API never blocks. At the start it can all run on one server.

### First real run (2026-10-22)

5 questions, 5/5 checks, $0.0027. The agent prompt (~4,360 tokens, mostly the value lists) is
~85% of the cost of a question.

## M1.4 — Worker + queue

### Looking inside Redis

`docker exec -it adaa-redis-1 redis-cli` opens Redis's command tool (like `psql`). `KEYS *`
lists keys (local only, never on a busy production Redis); `TYPE <key>`; `LLEN celery` and
`LRANGE celery 0 -1` show the waiting job slips; `XRANGE adaa:events:<question id> - +` shows
one question's progress events; `GET celery-task-meta-<job id>` shows a finished job's result;
`TTL <key>` shows seconds until it expires. Visual option: RedisInsight (free, official),
connected to 127.0.0.1:6379.

### Celery is a library, not a server

The queue lives in **Redis**. Celery is a Python library used in two places: the API uses it
to put a job slip into Redis, and the `celery worker` command starts worker processes that
take slips from Redis and call our task (`adaa.answer_question`). We never write the "pick a
job from the queue" loop; Celery's worker does it. The API and the workers never talk to each
other directly: both talk only to Redis (jobs) and Postgres (data).

```
Browser (React UI) → API (FastAPI) → Redis (queue) → workers ("celery worker") → Postgres + Claude
```

### Where each part runs

| Part | Laptop now | Production |
|---|---|---|
| UI (React) | browser + local dev server (M1.6) | static files on a CDN (S3 + CloudFront, Vercel) |
| API (FastAPI) | a process on the laptop (M1.5) | 2+ containers behind a load balancer |
| Redis (queue) | Docker container `adaa-redis-1` | managed service (e.g. AWS ElastiCache) |
| Workers | Docker container `adaa-worker-1` (2 processes) | a separate group of containers, scaled by queue length |
| Postgres (data) | Docker container `adaa-postgres-1` | managed database (e.g. AWS RDS) |
| Claude | Anthropic's cloud | Anthropic's cloud |
| Secrets | `.env` file | a secret manager |

In production the API and the workers run on different machines, so each side grows on its
own: more users → more API containers; a longer queue → more workers.

### The crash test (2026-10-23)

While a question was running, every worker process in the container was killed (SIGKILL).
The worker log showed: job received → `Process 'ForkPoolWorker-1' exited with signal 9` →
`WorkerLostError` → the same job id received again → a new process (`ForkPoolWorker-3`)
finished it with the correct answer. This is `task_acks_late` (the slip stays in Redis until
the job finishes) plus `task_reject_on_worker_lost` (a lost worker puts the slip back). The
price: a job can run twice ("at least once"), so a task must be safe to repeat — ours only
reads data, so a second run is harmless (it costs one more LLM call).

## M1.5 — API

### One question through the whole service

1. UI → `POST /questions` → the API creates the row in Postgres (`waiting`), queues a job with
   the same id, and answers 202 + the id at once.
2. UI opens `GET /questions/{id}/events` (SSE).
3. A worker takes the job: row `running` → a step event before each node (Redis Stream) →
   saves the answer, tokens and cost in the row (`done`) → publishes `done`.
4. The API sees `done`, reads the answer from the row (owner check), sends it, closes the stream.
5. A page reload later: `GET /questions/{id}` reads the answer straight from Postgres.

Where things live: question + answer → Postgres (kept); job slip → Redis queue (removed when
done); steps → Redis Stream (expires after 1 day).

### SSE (Server-Sent Events)

One HTTP connection the server keeps open and writes small messages into (`id:`, `event:`,
`data:`). One way only (server → browser), which is all a question needs. If the connection
drops, the browser reconnects by itself and sends `Last-Event-ID`, so no step is missed. A
`: still here` comment line every 15 s keeps proxies from closing a quiet stream. WebSockets
are for two-way traffic (voice, games, chat between people).

### First run through the API (2026-10-24)

5/5. Steps arrived live (understand 0.0 s → query 2.7 s → answer 2.9 s → done 4.3 s). The job
waited 0.015 s in the queue; the user waited 4.3 s in total. "Paris" stopped after the first
step. Cost ~$0.0011.

## M1.6 — React page

### How the page reaches the backend

The browser only knows one address, the Vite dev server (127.0.0.1:5173). The page calls
`/api/questions`; Vite's proxy passes it to the API on 127.0.0.1:8000 as `/questions`. One
address means no cross-site (CORS) rules are needed; in production a proxy (Caddy) does the
same job. The live steps use the browser's own `EventSource`, which reconnects by itself and
sends `Last-Event-ID`.

### One source of truth for the shapes

The TypeScript types are generated from FastAPI's OpenAPI description (`openapi-typescript`), so
the Pydantic models decide the shapes on both sides. After a backend change:
`uv run python -m adaa.api.openapi` (backend) then `npm run types` (frontend). A mismatch then
shows as a type error, not a broken page. The number formats are the one rule copied by hand
(`format.ts` ↔ `format_number`); both test files pin the same examples so they can't drift.

### npm audit and dev tools

`npm audit --omit=dev` only checks what users download. The dev tools (Vitest, esbuild) run on
the builder's machine and had real advisories, found by a full `npm audit`; upgrading Vite and
Vitest cleared them. Always run the full audit.

## M1.7 — Eval harness

### What an eval set is (and is not)

A sample that covers every KIND of question, not every question (people phrase things in
endless ways). 20 cases for M1; the same set grows every milestone, old cases stay, and every
real bug becomes a case. With 20 cases each one is 5%: big drops show, small differences don't.

### Plan vs answer, and why the right answers are hand-written SQL

The form is the LLM's plan; the table is the answer. The answer decides pass / fail; the plan is
compared as a hint. The right answers come from SQL written straight from the tables — if they
came from our compiler, a compiler bug would make the expected and the actual answer wrong in the
same way and the case would still pass (the builder's point). The SQL text itself is never
compared: two correct queries can look different. First check: the compiler agreed with the
hand-written SQL on all 18 answerable cases.

### Files and commands

| File | Changes when |
|---|---|
| `eval/questions/cases.yaml` | people edit it |
| `eval/questions/expected_results.json` | `uv run python -m adaa.evals.expected` |
| `eval/results/<date>_<time>.json` | `uv run python -m adaa.evals.run` (a new file every run) |

### First run (2026-10-25)

20 / 20, no hints, no template answers, $0.0107, p50 2.9 s, p95 3.5 s. A baseline, not proof.

## M2 step 1 — Full semantic layer

### Why add metrics at all

The agent can only answer what the semantic layer defines. Each rule is written once, so
"revenue" always means the same thing. A question outside it is refused with a reason, and
refusals show what to add next (cross-examination Q8). Very large domains split the layer by
business area or retrieve only the relevant definitions (Q9) — not needed for ADAA.

### Easy vs code metrics

- **YAML only:** items sold, active sellers, low-review rate, quarter.
- **New status rule `all`:** the cancellation rate counts every status (delivered only would
  make it 0), so a status filter or split is refused.
- **Two steps (`per` / `per_sql`):** the repeat-customer rate first counts orders per person,
  then takes the share of people with 2+. The compiler writes a query inside a query.

### Period comparison (`compare_to`)

The LLM decides *what* (two periods); code decides *how*. The form runs twice, Python joins
the rows by dimension value and computes change and change %. A rate changes in points. The
LLM never calculates: every calculation is a named, tested feature; anything else is refused.
"Compare 2017 and 2018" and "how did it grow" both mean `compare_to`; "revenue by year" is a
trend (a time breakdown).

### Support counts

A rate alone ("0.63%") hides the size. Code adds the counts behind it ("625 of 99,441 orders
canceled"; averages: "based on 99,224 reviews"). They go to the answer LLM and the number
guardrail, not to the table, so the eval is unchanged.

### Run (2026-10-26)

30 / 30, $0.0192, p50 2.9 s, p95 4.3 s. Weak spot found: the answer LLM sees only 20 rows, so
"fastest state" can be missed (noted in §0 to fix later).

## M2 step 2 — Router and quick routes

### Why a router

Before, every question went to the numbers flow, so "What was our profit?" or "Write a poem"
gave a weak plan or an error. The router first picks one of 5 routes: numbers, clarify,
refuse, off_topic, metadata. Its output is structured (one field, one of 5 values), never
free text.

### Jev first, Haiku as the fallback

Jev (TypeSafe) is a hosted classifier: it picks one choice and gives a confidence, but writes
no text. Common pattern: a small fast model routes, a larger model answers. In ADAA the
answer model is already the cheapest (Haiku), so the saving is small; the gain is a separate,
swappable router with a confidence score. The order is one config line
(`router.order: [route_jev, route_haiku]`). A failed option writes `router_fallback`; all
failing writes `router_failed` and the question goes to numbers. Jev is untested until the
OpenRouter key is added.

### After the router

One `reply` component with 3 prompts and 3 forms (clarify, refuse, metadata). Metadata: the
LLM picks only the topic; code writes the facts. Off-topic: no LLM, fixed text + 3 random
examples. Suggestions are full questions shown as buttons; a click is a new question (no
memory until M4). Suggestions are not checked before showing (builder's choice); the eval
asks each one ("suggestions answered").

### Eval: three ground truths per case

Route (`expected_route`, default numbers) → plan (`expected_form`, a hint) → answer (the
hand-written SQL table, or the exact code-written text, or the error kind). Clarify and
refuse texts have no fixed truth, so the route and the number of suggestions are checked.

### Run (2026-10-26)

44 / 44, routes 44 / 44, suggestions 9 / 9, $0.0367. The router adds ~1 s per question.
Lesson: an eval case that copies a prompt example proves little.

### Jev smoke test (2026-10-27)

3 questions straight to Jev: all routed right, 0.4–0.8 s, $0.000033 per call. A vague
question got confidence 0.61; clear ones 1.0. The full eval with Jev waits for the end of M2.

## M2 step 4 — Prompt caching

### What it is

The provider stores the start of a prompt. The next call that starts with the same bytes
reuses it: cheaper and often faster. The system prompt is the same for every question, so
it is cached; the question comes after the cache mark and is never cached.

### Write vs read

- **Cache write:** the first call (or the first after the cache expired) stores the prompt
  — 25% more than normal input ($0.125 vs $0.10 per 1M).
- **Cache read:** each later call within the TTL reuses it — 90% less ($0.01 per 1M).
  Each read resets the timer.
- Cost = input × $0.10 + output × $0.50 + cache_write × $0.125 + cache_read × $0.01
  (all / 1M). All four parts are always there; in one call either write or read is 0.

### Example (3,000-token prompt, 50-token question, 200-token answer)

No cache: $0.000405 per question. Question 1 (write): $0.000480. Question 2 (read):
$0.000135 — about 67% less. Two calls in 5 minutes already pay for the write.

### How we know it works

The provider does not return a cost, only token counts. On the second call
`cache_read_tokens` > 0 and `input_tokens` drops to the question only. If
`cache_read_tokens` stays 0, something changes the prompt (a date, a random ID): a broken
cache gives no error, only a higher bill — so check it after every prompt change.

### Why build it for ADAA (low traffic)

ADAA's saving is small: few users, so questions can be more than 5 minutes apart and the
cache expires. Built to learn the method; with many users the saving is large. Tools
(Langfuse, Helicone, the Anthropic Console) also show cost, but code still computes it
when it must act at once (quotas, cost limits, the eval report).

### Real check (2026-10-27)

2 agent calls, different questions: call 1 wrote 5,259 tokens ($0.000679); call 2 read
them ($0.000073, ~87% less than with no cache).

## M2 step 5 — Eval report format

### Two files per run

Each eval run writes `eval/results/<date-time>.json` and `<date-time>.md`. The JSON is for
code (compare runs, recompute); the `.md` is for a person: failures first, and for each case
the right answer and ADAA's answer side by side (route, plan, table, sentence). Old runs
stay, so runs can be compared over time.
