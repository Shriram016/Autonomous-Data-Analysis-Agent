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

**Why one ruff version:** the hook calls the project's own ruff via `uv run`, pinned in
`uv.lock`, so the hook, the editor and CI never disagree.
