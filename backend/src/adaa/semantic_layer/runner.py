"""Run a compiled query as adaa_query (read-only, 5 s per query) and return the result.

Answering a numbers question only needs to read, and the SQL comes from the LLM's form, so
this path always logs in as adaa_query: if anything upstream goes wrong, Postgres itself still
refuses any write. Other operations (memory, actions, loading) use their own code and roles.
"""

import time
from dataclasses import dataclass

import psycopg

from adaa.semantic_layer.compiler import CompiledQuery, compile_request
from adaa.semantic_layer.definitions import SemanticLayer, load
from adaa.semantic_layer.request import StructuredRequest
from adaa.settings import get_settings


class QueryTimeoutError(Exception):
    """The query ran past adaa_query's 5 s statement timeout."""


class DataUnavailableError(Exception):
    """Postgres could not be reached."""


TIMEOUT_MESSAGE = "That question took too long. Try a narrower time range or fewer breakdowns."
UNAVAILABLE_MESSAGE = "Data temporarily unavailable."


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[object, ...]]
    explanation: list[str]  # the "how I got this" lines from the compiler
    row_count: int
    elapsed_ms: int


def run_query(compiled: CompiledQuery, conninfo: str) -> QueryResult:
    started = time.perf_counter()
    try:
        with psycopg.connect(conninfo) as conn:
            conn.execute("SET search_path TO business")  # the SQL names tables without schema
            rows = [tuple(row) for row in conn.execute(compiled.sql, compiled.params).fetchall()]
    except psycopg.errors.QueryCanceled as e:  # the role's statement_timeout fired
        raise QueryTimeoutError(TIMEOUT_MESSAGE) from e
    except psycopg.OperationalError as e:  # connection refused or connect_timeout expired
        raise DataUnavailableError(UNAVAILABLE_MESSAGE) from e
    return QueryResult(
        columns=compiled.columns,
        rows=rows,
        explanation=compiled.explanation,
        row_count=len(rows),
        elapsed_ms=round((time.perf_counter() - started) * 1000),
    )


def answer_request(request: StructuredRequest, layer: SemanticLayer | None = None) -> QueryResult:
    """The whole numbers path: load definitions → compile the form → run it as adaa_query."""
    layer = layer or load()
    compiled = compile_request(request, layer)  # raises CompileError with a reason for people
    return run_query(compiled, get_settings().postgres_conninfo("query"))
