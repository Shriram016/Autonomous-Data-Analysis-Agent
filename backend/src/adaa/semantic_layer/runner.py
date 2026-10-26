"""Run a compiled query as adaa_query (read-only, 5 s per query) and return the result.

Answering a numbers question only needs to read, and the SQL comes from the LLM's form, so
this path always logs in as adaa_query: if anything upstream goes wrong, Postgres itself still
refuses any write. Other operations (memory, actions, loading) use their own code and roles.
"""

import time
from dataclasses import dataclass

import psycopg

from adaa.semantic_layer.compare import (
    comparison_columns,
    comparison_lines,
    merge_rows,
    split_comparison,
)
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
    # A rate's (part, whole) counts, one pair per row (CompiledQuery.with_support); else None.
    support: list[tuple[object, object]] | None = None


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
    support = None
    if compiled.with_support:  # keep rows as (dimensions…, metric); counts go aside
        support = [(row[-2], row[-1]) for row in rows]
        rows = [row[:-2] for row in rows]
    return QueryResult(
        columns=compiled.columns,
        rows=rows,
        explanation=compiled.explanation,
        row_count=len(rows),
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        support=support,
    )


def answer_request(request: StructuredRequest, layer: SemanticLayer | None = None) -> QueryResult:
    """The whole numbers path: load definitions → compile the form → run it as adaa_query.

    A comparison (compare_to) runs the form once per period and joins them (compare.py).
    """
    layer = layer or load()
    conninfo = get_settings().postgres_conninfo("query")
    if request.compare_to is None:
        # compile_request raises CompileError with a reason for people
        return run_query(compile_request(request, layer), conninfo)

    current, previous = split_comparison(request, layer)
    now = run_query(compile_request(current, layer), conninfo)
    before = run_query(compile_request(previous, layer), conninfo)
    unit = layer.metrics[request.metric].unit
    return QueryResult(
        columns=comparison_columns(now.columns, unit),
        rows=merge_rows(now.rows, before.rows, unit),
        explanation=[*now.explanation, *comparison_lines(request, unit)],
        row_count=now.row_count,
        elapsed_ms=now.elapsed_ms + before.elapsed_ms,
        support=now.support,  # the asked period's counts; rows keep its order
    )
