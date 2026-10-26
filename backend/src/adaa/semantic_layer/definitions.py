"""Load and check the semantic layer (the YAML files in semantic_layer/).

The YAML files are the single place where business words get an exact meaning (ADR 0003).
This module reads them into typed objects and refuses to load if a definition is wrong:
an unknown grain, a table that doesn't exist, a join that can't be reached, a business word
used twice, or a version mismatch between files. It also holds the grain rule that stops
double counting, and a fingerprint of the files that every answer can record (G6).

Check from backend/:  uv run python dev_checks/check_semantic_layer.py
"""

import hashlib
import re
from collections import deque
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, Field, model_validator

from adaa.ingestion.load_olist import TABLES
from adaa.settings import REPO_ROOT

LAYER_DIR = REPO_ROOT / "semantic_layer"
FILES = ("metrics.yaml", "dimensions.yaml", "joins.yaml", "defaults.yaml")
KNOWN_TABLES = frozenset(TABLES)

Grain = Literal["order", "item", "payment", "review"]
# How a metric's number is shown: 96,478 | R$ 5,067,633.16 | 6.77% | 12.5 days | 4.09
Unit = Literal["count", "BRL", "ratio", "days", "score"]
# The grain tree: each grain's parent. "order" is the top.
PARENT: dict[str, str | None] = {
    "order": None,
    "item": "order",
    "payment": "order",
    "review": "order",
}

STATUS_DIMENSION = "order_status"  # naming it in a form switches the D2 default off
DATE_PLACEHOLDER = "{date}"  # in a time dimension's SQL: the counted metric's own date column
ORDER_DATE = "orders.order_purchase_timestamp"

TABLE_REF = re.compile(r"\b([a-z_]+)\.[a-z_]+\b")  # "orders.order_status" → "orders"


class SemanticLayerError(Exception):
    """A definition in the YAML files is wrong; the layer does not load."""


class Support(BaseModel):
    """The counts behind a rate or an average, shown next to it for context:
    a rate has a part and a whole ("625 of 99,441 orders canceled"); an average has only
    the whole ("based on 99,224 reviews")."""

    whole_sql: str  # e.g. count(*)
    whole_label: str  # orders
    part_sql: str | None = None  # e.g. count(*) FILTER (WHERE orders.order_status = 'canceled')
    part_label: str | None = None  # canceled

    @model_validator(mode="after")
    def part_needs_both(self) -> Self:
        if (self.part_sql is None) != (self.part_label is None):
            raise ValueError("support needs both part_sql and part_label, or neither")
        return self

    def text(self, part: object, whole: object) -> str:
        if self.part_sql is None:
            return f"based on {int(str(whole)):,} {self.whole_label}"
        return f"{int(str(part)):,} of {int(str(whole)):,} {self.whole_label} {self.part_label}"


class Metric(BaseModel):
    label: str
    description: str
    grain: Grain
    table: str
    sql: str
    # v0.5.0 (§0 M2 3c): the date a period and the month / quarter / year breakdowns use —
    # the counted table's own date (reviews: the review date). Items and payments have none,
    # so they use the order date.
    date_column: str = ORDER_DATE
    # v0.5.0: True for a metric that counts DISTINCT ids (orders, customers). It may follow a
    # one-to-many join (joins.yaml `fans_out`), e.g. orders → order_items for "orders by
    # category", because each id is still counted once. Every other metric may not.
    fan_out_safe: bool = False
    # Two-step metrics (repeat-customer rate): `per_sql` is computed once per `per` value (one
    # row per person, named per_value), then `sql` runs over those rows. Both or neither.
    per: str | None = None
    per_sql: str | None = None
    filters: list[str] = []  # always applied: part of the definition
    # D2: "default" = delivered only unless the form names a status; "built_in" = the
    # filters already hold it and the form may not name a status; "all" = a share of orders
    # in every status (e.g. cancellation rate), so the form may not name a status either;
    # None = no status rule.
    status: Literal["default", "built_in", "all"] | None = None
    unit: Unit  # required: decides how the answer shows the number (agent/facts.py)
    support: Support | None = None  # a rate's counts, for context in the answer
    terms: list[str]
    shown_in_answer: str
    why: str | None = None


class Dimension(BaseModel):
    label: str
    grain: Grain
    sql: str
    terms: list[str]
    value_labels: dict[str, str] = {}  # stored code → name people say, e.g. PA → Pará
    kind: Literal["time"] | None = None  # time: a breakdown with no sort is oldest first
    why: str | None = None


class Join(BaseModel):
    from_table: str = Field(alias="from")
    to_table: str = Field(alias="to")
    condition: str  # not "on": YAML reads a bare `on` key as the boolean true
    optional: bool = False
    fans_out: bool = False  # one row → many rows: only fan_out_safe metrics may follow it


class Default(BaseModel):
    means: str
    terms: list[str] = []
    shown_in_answer: str
    why: str | None = None


class SemanticLayer(BaseModel):
    version: str
    fingerprint: str  # SHA-256 of the 4 files: proves which definitions produced an answer
    metrics: dict[str, Metric]
    dimensions: dict[str, Dimension]
    joins: list[Join]
    defaults: dict[str, Default]

    def dimension_sql(self, metric: str, dimension: str) -> str:
        """A dimension's SQL for this metric: a time dimension uses the metric's own date."""
        sql = self.dimensions[dimension].sql
        return sql.replace(DATE_PLACEHOLDER, self.metrics[metric].date_column)

    def can_use(self, metric: str, dimension: str) -> bool:
        """Grain rule: a dimension at the metric's own grain or above it never double counts.
        A fan_out_safe metric (counts DISTINCT ids) may use any dimension it can reach."""
        m = self.metrics[metric]
        if m.fan_out_safe:
            try:
                self.join_path(
                    m.table,
                    tables_in(self.dimension_sql(metric, dimension)) - {m.table},
                    fan_out=True,
                )
            except SemanticLayerError:
                return False
            return True
        grain: str | None = m.grain
        target = self.dimensions[dimension].grain
        while grain is not None:
            if grain == target:
                return True
            grain = PARENT[grain]
        return False

    def allows(self, metric: str, dimension: str) -> bool:
        """Every rule the compiler applies: the grain rule, and no status split for a metric
        whose definition already fixes the statuses (D2 built in, or every status)."""
        if dimension == STATUS_DIMENSION and self.metrics[metric].status in ("built_in", "all"):
            return False
        return self.can_use(metric, dimension)

    def join_path(self, start: str, needed: set[str], fan_out: bool = False) -> list[Join]:
        """The joins that reach every needed table from `start`, following many-to-one only
        (and one-to-many too when `fan_out`: only for metrics that count DISTINCT ids)."""
        edges: dict[str, list[Join]] = {}
        for join in self.joins:
            if fan_out or not join.fans_out:
                edges.setdefault(join.from_table, []).append(join)
        came_by: dict[str, Join | None] = {start: None}
        queue = deque([start])
        while queue:  # breadth-first: shortest path to each table
            table = queue.popleft()
            for join in edges.get(table, []):
                if join.to_table not in came_by:
                    came_by[join.to_table] = join
                    queue.append(join.to_table)
        missing = needed - came_by.keys()
        if missing:
            raise SemanticLayerError(f"No join path from {start} to {sorted(missing)}")
        path: list[Join] = []
        for table in sorted(needed):
            step = came_by[table]
            while step is not None and step not in path:
                path.insert(0, step)
                step = came_by[step.from_table]
        # order joins so each one starts from a table that is already joined
        ordered: list[Join] = []
        reached = {start}
        while len(ordered) < len(path):
            for join in path:
                if join not in ordered and join.from_table in reached:
                    ordered.append(join)
                    reached.add(join.to_table)
        return ordered


def tables_in(*sql_parts: str) -> set[str]:
    return {m.group(1) for part in sql_parts for m in TABLE_REF.finditer(part)}


def read_files(layer_dir: Path) -> tuple[dict[str, dict], str]:
    raw: dict[str, dict] = {}
    digest = hashlib.sha256()
    for name in FILES:
        text = (layer_dir / name).read_text(encoding="utf-8")
        digest.update(text.encode("utf-8"))
        raw[name] = yaml.safe_load(text) or {}
    return raw, digest.hexdigest()


def check(layer: SemanticLayer) -> None:
    problems: list[str] = []

    for join in layer.joins:
        for table in (join.from_table, join.to_table):
            if table not in KNOWN_TABLES:
                problems.append(f"join uses unknown table '{table}'")

    def check_tables(
        kind: str, name: str, start: str | None, sql_parts: list[str], fan_out: bool = False
    ) -> None:
        used = tables_in(*sql_parts)
        unknown = used - KNOWN_TABLES
        if unknown:
            problems.append(f"{kind} '{name}' uses unknown table(s) {sorted(unknown)}")
        elif start is not None:
            try:
                layer.join_path(start, used - {start}, fan_out=fan_out)
            except SemanticLayerError as e:
                problems.append(f"{kind} '{name}': {e}")

    for name, m in layer.metrics.items():
        if m.table not in KNOWN_TABLES:
            problems.append(f"metric '{name}' has unknown table '{m.table}'")
        two_step = [part for part in (m.per, m.per_sql) if part]
        if len(two_step) == 1:
            problems.append(f"metric '{name}' needs both 'per' and 'per_sql', or neither")
        support = [m.support.part_sql or "", m.support.whole_sql] if m.support else []
        parts = [m.sql, m.date_column, *two_step, *support, *m.filters]
        check_tables("metric", name, m.table, parts, fan_out=m.fan_out_safe)
    for name, d in layer.dimensions.items():
        check_tables("dimension", name, None, [d.sql])
        if (DATE_PLACEHOLDER in d.sql) != (d.kind == "time"):
            problems.append(f"dimension '{name}': only a time dimension uses {DATE_PLACEHOLDER}")

    owners: dict[str, str] = {}
    entries = [
        *(("metric", n, e.terms) for n, e in layer.metrics.items()),
        *(("dimension", n, e.terms) for n, e in layer.dimensions.items()),
        *(("default", n, e.terms) for n, e in layer.defaults.items()),
    ]
    for kind, name, terms in entries:
        for term in terms:
            key = term.strip().lower()
            if key in owners:
                problems.append(f"term '{term}' is used by {owners[key]} and {kind} '{name}'")
            owners[key] = f"{kind} '{name}'"

    if problems:
        raise SemanticLayerError("Semantic layer not loaded:\n- " + "\n- ".join(problems))


def load(layer_dir: Path = LAYER_DIR) -> SemanticLayer:
    raw, fingerprint = read_files(layer_dir)
    versions = {name: str(data.get("version")) for name, data in raw.items()}
    if len(set(versions.values())) != 1:
        raise SemanticLayerError(f"Files have different versions: {versions}")
    try:
        layer = SemanticLayer(
            version=versions["metrics.yaml"],
            fingerprint=fingerprint,
            metrics=raw["metrics.yaml"].get("metrics", {}),
            dimensions=raw["dimensions.yaml"].get("dimensions", {}),
            joins=raw["joins.yaml"].get("joins", []),
            defaults=raw["defaults.yaml"].get("defaults", {}),
        )
    except ValueError as e:  # pydantic's ValidationError: a missing field or a bad grain
        raise SemanticLayerError(f"Semantic layer not loaded:\n{e}") from e
    check(layer)
    return layer
