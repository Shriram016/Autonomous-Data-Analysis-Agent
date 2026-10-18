"""Postgres (+pgvector) and Redis are up and usable. Needs: docker compose up (see infra/)."""

import psycopg
import pytest
import redis

from adaa.settings import get_settings

pytestmark = pytest.mark.integration

SCHEMAS = {"business", "agent", "conversation", "staging"}


def test_postgres_has_schemas_and_vector_search() -> None:
    with psycopg.connect(get_settings().postgres_conninfo()) as conn:
        found = {
            row[0]
            for row in conn.execute(
                "SELECT schema_name FROM information_schema.schemata"
            ).fetchall()
        }
        assert found >= SCHEMAS

        conn.execute("CREATE TEMP TABLE probe (id int, v vector(3))")
        conn.execute("INSERT INTO probe VALUES (1, '[1,0,0]'), (2, '[0,1,0]')")
        nearest = conn.execute(
            "SELECT id FROM probe ORDER BY v <-> '[0.9,0.1,0]' LIMIT 1"
        ).fetchone()
        assert nearest == (1,)


def test_redis_round_trip() -> None:
    client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
    assert client.ping()
    client.set("adaa:probe", "ok", ex=10)
    assert client.get("adaa:probe") == b"ok"
