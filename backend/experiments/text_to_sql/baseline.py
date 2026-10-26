"""The text-to-SQL baseline: the LLM writes the SQL itself (§0 M2 step 3, slice 3a).

NOT part of the product. It exists only to measure our method (the LLM fills a form, the
semantic layer writes the SQL) against the simple method many teams start with. To keep the
comparison fair, only the method changes: the same model (Haiku 5.5, job `text_to_sql`),
the same "today" (the data date), the same read-only role and 5 s limit, no new library.

Two variants of the prompt:
    A — the table descriptions only (tables, columns, types, keys, how they connect)
    B — the same + a short list of business rules (rules.md)

No retry, not even after an SQL error: a simple baseline (builder's choice, 2026-10-26).
"""

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Self

import psycopg
from pydantic import BaseModel, ConfigDict, model_validator

from adaa.agent.prompts import Prompt, load_prompt
from adaa.llm.adapters.base import Adapter, Message
from adaa.llm.complete import NO_USAGE, complete
from adaa.llm.types import LlmError, Usage
from adaa.semantic_layer.definitions import SemanticLayer
from adaa.semantic_layer.request import MAX_LIMIT
from adaa.settings import REPO_ROOT

HERE = REPO_ROOT / "backend" / "experiments" / "text_to_sql"
Variant = Literal["A", "B"]

# The columns of every business table, in order. pg_catalog (not information_schema) for the
# primary keys: information_schema hides constraints from roles that don't own the table.
COLUMNS_SQL = """
SELECT c.table_name, c.column_name, c.data_type,
       EXISTS (
         SELECT 1 FROM pg_index i
         JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
         WHERE i.indisprimary AND i.indrelid = ('business.' || c.table_name)::regclass
           AND a.attname = c.column_name
       ) AS is_key
FROM information_schema.columns c
WHERE c.table_schema = 'business'
ORDER BY c.table_name, c.ordinal_position
"""

Column = tuple[str, str, str, bool]  # table, column, type, part of the primary key


class SqlForm(BaseModel):
    """What the LLM fills: a query, or the reason it can't write one. Exactly one."""

    model_config = ConfigDict(extra="forbid")

    sql: str | None = None
    cannot_answer: str | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> Self:
        if (self.sql is None) == (self.cannot_answer is None):
            raise ValueError("fill exactly one of sql and cannot_answer")
        return self


@dataclass
class BaselineAnswer:
    question: str
    variant: Variant
    sql: str | None = None
    cannot_answer: str | None = None
    rows: list[tuple[object, ...]] = field(default_factory=list)
    error: str | None = None  # llm_failed, not_a_select, sql_error, timeout, data_unavailable
    usage: Usage = NO_USAGE
    seconds: float = 0.0


# ---------- the prompt ----------


def tables_text(columns: list[Column]) -> str:
    """One line per table: orders(order_id text KEY, customer_id text, …)."""
    tables: dict[str, list[str]] = {}
    for table, column, data_type, is_key in columns:
        tables.setdefault(table, []).append(f"{column} {data_type}{' KEY' if is_key else ''}")
    return "\n".join(f"- {table}({', '.join(cols)})" for table, cols in tables.items())


def joins_text(layer: SemanticLayer) -> str:
    """How the tables connect: table structure, not business rules (from joins.yaml)."""
    return "\n".join(f"- {j.condition}" for j in layer.joins)


def build_prompt(
    variant: Variant, columns: list[Column], layer: SemanticLayer, today: date
) -> Prompt:
    rules = load_prompt("rules", {}, prompts_dir=HERE).text if variant == "B" else ""
    values = {
        "tables": tables_text(columns),
        "joins": joins_text(layer),
        "rules": rules,
        "today": today.isoformat(),
    }
    return load_prompt("prompt", values, prompts_dir=HERE)


def read_columns(conninfo: str) -> list[Column]:
    with psycopg.connect(conninfo) as conn:
        return [tuple(row) for row in conn.execute(COLUMNS_SQL).fetchall()]


# ---------- one question ----------


def is_select(sql: str) -> bool:
    first = sql.lstrip().split(None, 1)[0].lower() if sql.strip() else ""
    return first in ("select", "with")


def run_sql(sql: str, conninfo: str) -> tuple[list[tuple[object, ...]], str | None]:
    """Rows, or an error kind. As adaa_query: read-only, 5 s per query (role settings).
    No params: the LLM's SQL may hold a literal % (LIKE '%x%')."""
    try:
        with psycopg.connect(conninfo) as conn:
            conn.execute("SET search_path TO business")
            cursor = conn.execute(sql.encode("utf-8"))  # bytes: never parsed for %s
            return [tuple(row) for row in cursor.fetchmany(MAX_LIMIT)], None
    except psycopg.errors.QueryCanceled:
        return [], "timeout"
    except psycopg.OperationalError:
        return [], "data_unavailable"
    except psycopg.Error:
        return [], "sql_error"


def ask_baseline(
    question: str,
    variant: Variant,
    prompt: Prompt,
    conninfo: str,
    adapter: Adapter | None = None,
) -> BaselineAnswer:
    started = time.monotonic()
    answer = BaselineAnswer(question=question, variant=variant)
    messages = [
        Message(role="system", content=prompt.text),
        Message(role="user", content=question),
    ]
    try:
        reply = complete("text_to_sql", messages, SqlForm, adapter=adapter)
    except LlmError:
        answer.error = "llm_failed"
    else:
        answer.usage = reply.usage
        answer.sql, answer.cannot_answer = reply.output.sql, reply.output.cannot_answer
        if answer.sql is not None:
            if is_select(answer.sql):
                answer.rows, answer.error = run_sql(answer.sql, conninfo)
            else:
                answer.error = "not_a_select"
    answer.seconds = round(time.monotonic() - started, 2)
    return answer
