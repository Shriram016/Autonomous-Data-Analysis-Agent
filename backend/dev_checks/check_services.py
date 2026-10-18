"""M0.2 check: Postgres (+pgvector) and Redis are running and usable.

Start services first (from repo root):
    docker compose -f infra/docker-compose.yml --env-file .env up -d
Then run from backend/:
    uv run python dev_checks/check_services.py
"""

import psycopg
import redis

from adaa.settings import get_settings

SCHEMAS = ["business", "agent", "conversation", "staging"]


def check_postgres(conninfo: str) -> None:
    with psycopg.connect(conninfo) as conn:
        version = conn.execute("SHOW server_version").fetchone()
        print(f"Postgres:   version {version[0] if version else '?'}")

        vector = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        assert vector, "pgvector extension missing (did init.sql run?)"
        print(f"pgvector:   version {vector[0]}")

        rows = conn.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = ANY(%s)",
            (SCHEMAS,),
        ).fetchall()
        found = sorted(r[0] for r in rows)
        assert found == sorted(SCHEMAS), f"schemas found: {found}"
        print(f"Schemas:    {', '.join(found)}")

        # Tiny vector search: which stored vector is closest to the query?
        conn.execute("CREATE TEMP TABLE probe (id int, label text, v vector(3))")
        conn.execute(
            "INSERT INTO probe VALUES"
            " (1, 'late delivery', '[1,0,0]'), (2, 'damaged item', '[0,1,0]')"
        )
        nearest = conn.execute(
            "SELECT label FROM probe ORDER BY v <-> '[0.9,0.1,0]' LIMIT 1"
        ).fetchone()
        assert nearest == ("late delivery",), f"unexpected nearest: {nearest}"
        print("Vector search: nearest to [0.9,0.1,0] is 'late delivery'")


def check_redis(url: str) -> None:
    client = redis.Redis.from_url(url, socket_connect_timeout=2)
    assert client.ping()
    client.set("adaa:probe", "ok", ex=10)
    assert client.get("adaa:probe") == b"ok"
    aof = client.config_get("appendonly").get("appendonly")
    print(f"Redis:      ping ok, set/get ok, AOF persistence = {aof}")


def main() -> None:
    settings = get_settings()
    check_postgres(settings.postgres_conninfo())
    check_redis(settings.redis_url)
    print("M0.2 services check passed.")


if __name__ == "__main__":
    main()
