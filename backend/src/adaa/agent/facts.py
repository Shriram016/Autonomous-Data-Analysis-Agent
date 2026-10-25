"""Turn a query result into ready-to-use text (§0 M1.3, answer with a number guardrail).

The code, not the LLM, formats every number and computes every derived fact, so the answer
LLM only puts given strings into sentences. How a value is shown comes from the semantic
layer, never from guessing the data: the metric column is formatted by the metric's `unit`,
a dimension column by its name (month → 2017-03) and its `value_labels` (SP → SP (São Paulo)).

The result also gives the template answer: a plain sentence made by code, shown when the
answer LLM fails or breaks the number guardrail. It is not pretty, but it is always correct.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from adaa.semantic_layer.definitions import SemanticLayer, Unit
from adaa.semantic_layer.request import MAX_LIMIT, StructuredRequest
from adaa.semantic_layer.runner import QueryResult

TEMPLATE_ROWS = 5  # rows named in the template sentence; the table below shows them all
MAX_BARS = 20  # a bar chart shows the top 20; more bars can't be read


def format_number(value: object, unit: Unit) -> str:
    number = Decimal(str(value))
    match unit:
        case "count":
            return f"{int(number):,}"
        case "BRL":
            return f"R$ {number:,.2f}"
        case "ratio":
            return f"{number * 100:.2f}%"
        case "days":
            return f"{number:.1f} days"
        case "score":
            return f"{number:.2f}"


def format_dimension(value: object, dimension: str, layer: SemanticLayer) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, datetime | date):
        return value.strftime("%Y-%m") if dimension == "month" else value.isoformat()
    if isinstance(value, Decimal) and value == value.to_integral_value():
        value = int(value)  # extract(year ...) gives 2017, not 2017.0
    name = layer.dimensions[dimension].value_labels.get(str(value))
    return f"{value} ({name})" if name else str(value)


class Facts(BaseModel):
    """Everything the answer step needs, already formatted."""

    model_config = ConfigDict(frozen=True)

    metric_label: str
    headers: list[str]  # dimension labels, then the metric label
    rows: list[list[str]]  # formatted, at most max_rows (the LLM's share)
    total_rows: int  # rows in the full result
    total: str | None  # sum of all rows, only where adding rows is correct
    template_answer: str

    @property
    def allowed_numbers(self) -> list[str]:
        """Every string the answer may quote numbers from (the guardrail's list)."""
        values = [cell for row in self.rows for cell in row]
        values += [str(self.total_rows), str(len(self.rows))]
        return values + ([self.total] if self.total else [])

    def result_text(self) -> str:
        """The result as the answer LLM sees it."""
        shown = len(self.rows)
        if self.total_rows == 0:
            return "Result: no rows."
        head = (
            f"Result (top {shown} of {self.total_rows} rows):"
            if shown < self.total_rows
            else f"Result ({self.total_rows} row{'' if self.total_rows == 1 else 's'}):"
        )
        lines = [head, " | ".join(self.headers), *(" | ".join(row) for row in self.rows)]
        if self.total:
            lines.append(f"Total {self.metric_label.lower()} of all rows: {self.total}")
        return "\n".join(lines)


def can_add_rows(request: StructuredRequest, layer: SemanticLayer, result: QueryResult) -> bool:
    """A total of the rows is correct only for a sum metric, over a complete breakdown.

    A rate or an average can't be added; count(DISTINCT ...) counts an order once per
    category, so adding categories counts it twice. The grain rule already makes every
    allowed breakdown of a sum metric split it cleanly. A limit (or the 1,000-row cap)
    would make the sum cover only part of the data.
    """
    metric = layer.metrics[request.metric]
    complete = request.limit is None and result.row_count < MAX_LIMIT
    return bool(request.dimensions) and metric.sql.startswith("sum(") and complete


def template_answer(
    label: str, headers: list[str], rows: list[list[str]], total_rows: int, total: str | None
) -> str:
    if total_rows == 0:
        return "No data matched the question."
    if len(headers) == 1:  # no breakdown: a single number
        return f"{label}: {rows[0][0]}."
    named = [f"{', '.join(row[:-1])}: {row[-1]}" for row in rows[:TEMPLATE_ROWS]]
    by = ", ".join(h.lower() for h in headers[:-1])
    scope = f"top {len(named)} of {total_rows}" if len(named) < total_rows else f"{total_rows} rows"
    sentence = f"{label} by {by} ({scope}): {'; '.join(named)}."
    return f"{sentence} Total: {total}." if total else sentence


def build_facts(
    result: QueryResult, request: StructuredRequest, layer: SemanticLayer, max_rows: int
) -> Facts:
    metric = layer.metrics[request.metric]
    headers = [layer.dimensions[d].label for d in request.dimensions] + [metric.label]
    rows = [
        [format_dimension(v, d, layer) for v, d in zip(row[:-1], request.dimensions, strict=True)]
        + [format_number(row[-1], metric.unit) if row[-1] is not None else "no value"]
        for row in result.rows[:max_rows]
    ]
    total = None
    if can_add_rows(request, layer, result):
        total = format_number(sum(Decimal(str(row[-1] or 0)) for row in result.rows), metric.unit)
    return Facts(
        metric_label=metric.label,
        headers=headers,
        rows=rows,
        total_rows=result.row_count,
        total=total,
        template_answer=template_answer(metric.label, headers, rows, result.row_count, total),
    )


# ---------- the chart (§0 M1.6: automatic, chosen by code, never by the LLM) ----------


class ChartPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: str  # the dimension value as shown in the table, e.g. "2017-03" or "SP (São Paulo)"
    y: float  # the raw number; the page formats it with `unit`, like the table


class Chart(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["line", "bar"]
    x_label: str
    y_label: str
    unit: Unit
    points: list[ChartPoint]


def build_chart(
    result: QueryResult, request: StructuredRequest, layer: SemanticLayer
) -> Chart | None:
    """A chart when the result suits one: 1 time breakdown → line, 1 category → bar.

    A single number gains nothing from a chart; 2 breakdowns need a chart with several
    lines or groups, which comes later. The table always shows every row.
    """
    if len(request.dimensions) != 1 or result.row_count == 0:
        return None
    dimension = request.dimensions[0]
    metric = layer.metrics[request.metric]
    kind: Literal["line", "bar"] = "line" if layer.dimensions[dimension].kind == "time" else "bar"
    points = [
        ChartPoint(x=format_dimension(row[0], dimension, layer), y=float(str(row[-1])))
        for row in result.rows
        if row[-1] is not None
    ]
    if kind == "line":
        points.sort(key=lambda p: p.x)  # a trend reads oldest first, even after "top 5 months"
    else:
        points = points[:MAX_BARS]  # rows already come highest first
    return Chart(
        kind=kind,
        x_label=layer.dimensions[dimension].label,
        y_label=metric.label,
        unit=metric.unit,
        points=points,
    )
