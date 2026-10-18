# V3 learning notes

Plain-language explanations of concepts that came up while building V3, plus questions to learn
later. Interview-style system-design questions live in [v3-cross-examination.md](v3-cross-examination.md).

## Learn later

- Rate limiter internals (token bucket) — from failure-handling design
- Connection pools and PgBouncer — from database failure design
- Atomic publish and data versioning — from daily-publish design

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

### Redis AOF

Append-only file: Redis writes every change to disk, so queued jobs survive a restart instead of
vanishing (locked in the failure design).

---

**Why one ruff version:** the hook calls the project's own ruff via `uv run`, pinned in
`uv.lock`, so the hook, the editor and CI never disagree.
