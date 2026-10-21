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
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from adaa.ingestion.load_olist import TABLES
from adaa.settings import REPO_ROOT

LAYER_DIR = REPO_ROOT / "semantic_layer"
FILES = ("metrics.yaml", "dimensions.yaml", "joins.yaml", "defaults.yaml")
KNOWN_TABLES = frozenset(TABLES)

Grain = Literal["order", "item", "payment", "review"]
# The grain tree: each grain's parent. "order" is the top.
PARENT: dict[str, str | None] = {
    "order": None,
    "item": "order",
    "payment": "order",
    "review": "order",
}

TABLE_REF = re.compile(r"\b([a-z_]+)\.[a-z_]+\b")  # "orders.order_status" → "orders"


class SemanticLayerError(Exception):
    """A definition in the YAML files is wrong; the layer does not load."""


class Metric(BaseModel):
    label: str
    description: str
    grain: Grain
    table: str
    sql: str
    filters: list[str] = []  # always applied: part of the definition
    # D2: "default" = delivered only unless the form names a status; "built_in" = the
    # filters already hold it and the form may not name a status; None = no status rule.
    status: Literal["default", "built_in"] | None = None
    unit: str | None = None
    terms: list[str]
    shown_in_answer: str
    why: str | None = None


class Dimension(BaseModel):
    label: str
    grain: Grain
    sql: str
    terms: list[str]
    value_labels: dict[str, str] = {}  # stored code → name people say, e.g. PA → Pará
    why: str | None = None


class Join(BaseModel):
    from_table: str = Field(alias="from")
    to_table: str = Field(alias="to")
    condition: str  # not "on": YAML reads a bare `on` key as the boolean true
    optional: bool = False


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

    def can_use(self, metric: str, dimension: str) -> bool:
        """Grain rule: a dimension at the metric's own grain or above it never double counts."""
        grain: str | None = self.metrics[metric].grain
        target = self.dimensions[dimension].grain
        while grain is not None:
            if grain == target:
                return True
            grain = PARENT[grain]
        return False

    def join_path(self, start: str, needed: set[str]) -> list[Join]:
        """The joins that reach every needed table from `start`, following many-to-one only."""
        edges: dict[str, list[Join]] = {}
        for join in self.joins:
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

    def check_tables(kind: str, name: str, start: str | None, sql_parts: list[str]) -> None:
        used = tables_in(*sql_parts)
        unknown = used - KNOWN_TABLES
        if unknown:
            problems.append(f"{kind} '{name}' uses unknown table(s) {sorted(unknown)}")
        elif start is not None:
            try:
                layer.join_path(start, used - {start})
            except SemanticLayerError as e:
                problems.append(f"{kind} '{name}': {e}")

    for name, m in layer.metrics.items():
        if m.table not in KNOWN_TABLES:
            problems.append(f"metric '{name}' has unknown table '{m.table}'")
        check_tables("metric", name, m.table, [m.sql, *m.filters])
    for name, d in layer.dimensions.items():
        check_tables("dimension", name, None, [d.sql])

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
