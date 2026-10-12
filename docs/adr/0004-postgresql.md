# Data lives in PostgreSQL

Business data and the agent's own tables live in PostgreSQL. The database itself enforces least privilege (read-only role on business data, narrow write role on agent-owned tables) and per-query time limits, so even buggy code cannot break those rules; it also handles 100 concurrent users and can store review vectors via pgvector.

## Considered Options

- **DuckDB** — faster for pure analytics and zero setup, but embedded in the app process with no user accounts or permissions, so it cannot enforce who may do what. Rejected.
- **SQLite** — too limited for permissions, concurrent use and analytics; reads as a toy. Rejected.

## Consequences

- Docker is required locally (also needed for deployment).
- Loading Olist becomes an ingestion step into PostgreSQL.
- Whether review vectors also live here (pgvector) is a separate decision.

## Questions that drove this

- Which locked requirements does the store have to enforce, and should the code or the database enforce them?
- How many concurrent users must it serve?
- Can the same store serve both numbers and review search?
