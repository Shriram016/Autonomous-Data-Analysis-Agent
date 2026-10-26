"""Period comparison: "revenue by state, 2018 vs 2017" (§0 M2 step 1, slice C).

The form names two periods: `period` (the one asked about) and `compare_to` (the one to
compare it with). The same form runs twice, once per period, through the normal compiler
and runner. Then code — never the LLM, never SQL — joins the two results row by row and
computes the change. So every metric works the same way, two-step metrics included.

Rows follow the asked period: "top 5 states in 2018 vs 2017" keeps 2018's top 5 and looks
up each one's 2017 value, so the second query runs with no sort and no limit.
A rate changes in points (6.8% → 8.1% is +1.3 points), so it gets no change %.
"""

from collections.abc import Sequence
from decimal import Decimal

from adaa.semantic_layer.compiler import CompileError
from adaa.semantic_layer.definitions import SemanticLayer, Unit
from adaa.semantic_layer.request import StructuredRequest

PREVIOUS = "previous"  # result column names after the metric's own column
CHANGE = "change"
CHANGE_PCT = "change_pct"

Row = tuple[object, ...]


def has_change_pct(unit: Unit) -> bool:
    return unit != "ratio"


def split_comparison(
    request: StructuredRequest, layer: SemanticLayer
) -> tuple[StructuredRequest, StructuredRequest]:
    """The two ordinary forms: the asked period, and the compare_to period."""
    assert request.compare_to is not None
    for name in request.dimensions:
        if layer.dimensions[name].kind == "time":  # 2018-03 and 2017-03 would never match
            label = layer.dimensions[name].label.lower()
            raise CompileError(
                f"A comparison of two periods can't also be split by {label}. "
                f"Ask for the trend by {label} instead."
            )
    current = request.model_copy(update={"compare_to": None})
    previous = request.model_copy(
        update={"period": request.compare_to, "compare_to": None, "sort": None, "limit": None}
    )
    return current, previous


def change(now: object, before: object, unit: Unit) -> tuple[Decimal | None, ...]:
    """(change, change %) or (change,) for a rate. No value when a period has no value;
    no change % when the earlier value is 0."""
    if now is None or before is None:
        return (None, None) if has_change_pct(unit) else (None,)
    diff = Decimal(str(now)) - Decimal(str(before))
    if not has_change_pct(unit):
        return (diff,)
    before_value = Decimal(str(before))
    return diff, (diff / before_value if before_value else None)


def merge_rows(current: Sequence[Row], previous: Sequence[Row], unit: Unit) -> list[Row]:
    """Each row of the asked period + its earlier value + the change. Dimension values are
    the key; a row missing from the earlier period gets no earlier value."""
    earlier = {row[:-1]: row[-1] for row in previous}
    merged = []
    for row in current:
        before = earlier.get(row[:-1])
        merged.append((*row, before, *change(row[-1], before, unit)))
    return merged


def comparison_columns(columns: list[str], unit: Unit) -> list[str]:
    return [*columns, PREVIOUS, CHANGE, *([CHANGE_PCT] if has_change_pct(unit) else [])]


def comparison_lines(request: StructuredRequest, unit: Unit) -> list[str]:
    """The "how I got this" lines a comparison adds."""
    assert request.compare_to is not None
    rule = (
        "Change = the difference in percentage points."
        if not has_change_pct(unit)
        else "Change = asked period minus earlier period; change % = change / earlier period."
    )
    return [f"Compared with: {request.compare_to.start} to {request.compare_to.end}.", rule]
