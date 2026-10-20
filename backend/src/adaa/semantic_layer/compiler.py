"""Compile a structured request into safe SQL, using the semantic layer.

The LLM fills in the form (request.py); it never names tables or writes SQL. This module:

1. looks up every name in the form (metric, dimensions, filters, sort),
2. applies the grain rule, so nothing is double counted,
3. collects the tables the definitions need and finds the joins (joins.yaml),
4. builds WHERE from the metric's own filters, the period and the manager's filters,
5. adds GROUP BY, ORDER BY and LIMIT,
6. writes the "how I got this" explanation.

Every value from the form goes into `params`, never into the SQL text, so a value can never
become a command (SQL injection). It returns the SQL; running it is runner.py's job.
"""

from dataclasses import dataclass
from datetime import timedelta

from adaa.semantic_layer.definitions import SemanticLayer, tables_in
from adaa.semantic_layer.request import MAX_LIMIT, Filter, StructuredRequest

PERIOD_COLUMN = "orders.order_purchase_timestamp"  # a period always means the order date
SQL_OPERATORS = {"=": "=", "!=": "<>", "in": "IN", "not in": "NOT IN"}


class CompileError(Exception):
    """The form asks for something the semantic layer can't answer. The message is for people."""


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: dict[str, object]
    columns: list[str]  # result column names, in order: dimensions first, then the metric
    explanation: list[str]  # the "how I got this" lines


# ---------- 1–2: names and grain ----------


def look_up_names(request: StructuredRequest, layer: SemanticLayer) -> None:
    if request.metric not in layer.metrics:
        raise CompileError(
            f"No metric called '{request.metric}'. Known metrics: {', '.join(layer.metrics)}."
        )
    used = request.dimensions + [f.dimension for f in request.filters]
    for name in used:
        if name not in layer.dimensions:
            raise CompileError(
                f"No dimension called '{name}'. Known dimensions: {', '.join(layer.dimensions)}."
            )
    if request.sort and request.sort.by not in [request.metric, *request.dimensions]:
        raise CompileError(
            f"Can't sort by '{request.sort.by}': sort by the metric or one of the breakdowns."
        )


def check_grain(request: StructuredRequest, layer: SemanticLayer) -> None:
    metric = layer.metrics[request.metric]
    for name in request.dimensions + [f.dimension for f in request.filters]:
        if not layer.can_use(request.metric, name):
            dim = layer.dimensions[name]
            raise CompileError(
                f"{metric.label} is counted per {metric.grain}, and one {metric.grain} can have "
                f"several {dim.label.lower()} values, so it would be counted twice. "
                f"{metric.label} can't be split by {dim.label.lower()}."
            )


# ---------- 3: tables and joins ----------


def needed_tables(request: StructuredRequest, layer: SemanticLayer) -> set[str]:
    metric = layer.metrics[request.metric]
    parts = [metric.sql, *metric.filters]
    if request.period:  # a period filters on the order date, so it needs the orders table
        parts.append(PERIOD_COLUMN)
    parts += [layer.dimensions[d].sql for d in request.dimensions]
    parts += [layer.dimensions[f.dimension].sql for f in request.filters]
    return tables_in(*parts)


def build_joins(request: StructuredRequest, layer: SemanticLayer) -> str:
    start = layer.metrics[request.metric].table
    path = layer.join_path(start, needed_tables(request, layer) - {start})
    return "\n".join(
        f"  {'LEFT JOIN' if j.optional else 'JOIN'} {j.to_table} ON {j.condition}" for j in path
    )


# ---------- 4: WHERE ----------


def build_period(
    request: StructuredRequest, layer: SemanticLayer, params: dict[str, object]
) -> tuple[str | None, str]:
    """WHERE condition for the period (None = all data), and its explanation line."""
    if request.period is None:  # no period asked for → all available data (defaults.yaml)
        return None, layer.defaults["default_period"].shown_in_answer
    start, end = request.period.start, request.period.end
    params["period_start"] = start
    params["period_end"] = end + timedelta(days=1)  # "before the next day" includes all of `end`
    condition = f"{PERIOD_COLUMN} >= %(period_start)s AND {PERIOD_COLUMN} < %(period_end)s"
    return condition, f"Period: {start} to {end}."


def build_filter(index: int, f: Filter, layer: SemanticLayer, params: dict[str, object]) -> str:
    names = []
    for j, value in enumerate(f.values):
        name = f"f{index}_{j}"
        params[name] = value
        names.append(f"%({name})s")
    column = layer.dimensions[f.dimension].sql
    if f.op in ("=", "!="):
        return f"{column} {SQL_OPERATORS[f.op]} {names[0]}"
    return f"{column} {SQL_OPERATORS[f.op]} ({', '.join(names)})"


def build_where(
    request: StructuredRequest, layer: SemanticLayer, params: dict[str, object]
) -> tuple[list[str], str]:
    conditions = list(layer.metrics[request.metric].filters)  # e.g. delivered only (D2)
    period_condition, period_line = build_period(request, layer, params)
    if period_condition:
        conditions.append(period_condition)
    conditions += [build_filter(i, f, layer, params) for i, f in enumerate(request.filters)]
    return conditions, period_line


# ---------- 5: ORDER BY and LIMIT ----------


def build_order_and_limit(request: StructuredRequest) -> tuple[str, int]:
    limit = request.limit or MAX_LIMIT
    if request.sort:
        order = f"ORDER BY {request.sort.by} {request.sort.direction.upper()}"
    elif request.dimensions:
        order = f"ORDER BY {request.metric} DESC"  # breakdown with no sort: highest first
    else:
        order = ""
    return order, limit


# ---------- 6: explanation ----------


def build_explanation(
    request: StructuredRequest, layer: SemanticLayer, period_line: str
) -> list[str]:
    lines = [layer.metrics[request.metric].shown_in_answer]
    if request.dimensions:
        labels = ", ".join(layer.dimensions[d].label for d in request.dimensions)
        lines.append(f"Broken down by: {labels}.")
    lines.append(period_line)
    for f in request.filters:
        values = ", ".join(str(v) for v in f.values)
        lines.append(f"Filter: {layer.dimensions[f.dimension].label} {f.op} {values}.")
    if request.limit:
        lines.append(f"Showing at most {request.limit} rows.")
    lines.append(
        f"Definitions: semantic layer v{layer.version} (fingerprint {layer.fingerprint[:12]})."
    )
    return lines


# ---------- the one function other code calls ----------


def compile_request(request: StructuredRequest, layer: SemanticLayer) -> CompiledQuery:
    look_up_names(request, layer)
    check_grain(request, layer)

    metric = layer.metrics[request.metric]
    params: dict[str, object] = {}
    conditions, period_line = build_where(request, layer, params)
    order, limit = build_order_and_limit(request)
    params["row_limit"] = limit

    select = [f"{layer.dimensions[d].sql} AS {d}" for d in request.dimensions]
    select.append(f"{metric.sql} AS {request.metric}")
    lines = [
        "SELECT " + ",\n       ".join(select),
        f"FROM {metric.table}",
        build_joins(request, layer),
        ("WHERE " + "\n  AND ".join(conditions)) if conditions else "",
    ]
    if request.dimensions:
        lines.append("GROUP BY " + ", ".join(layer.dimensions[d].sql for d in request.dimensions))
    if order:
        lines.append(order)
    lines.append("LIMIT %(row_limit)s")

    return CompiledQuery(
        sql="\n".join(line for line in lines if line),
        params=params,
        columns=[*request.dimensions, request.metric],
        explanation=build_explanation(request, layer, period_line),
    )
