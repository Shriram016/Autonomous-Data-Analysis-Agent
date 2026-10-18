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

**Not in the hook:** tests and mypy (slower) — they run in CI on every push and during each
slice. The hook stays under a second so committing never feels slow.

**Why one ruff version:** the hook calls the project's own ruff via `uv run`, pinned in
`uv.lock`, so the hook, the editor and CI never disagree.
