"""Value linking: which values each dimension really holds (§0 M1.3, Value linking).

The model knows dimension names, not the values stored in them: it may write "toy" where the
data says `toys`. A wrong value still runs and returns an empty answer that looks right, so
two layers protect against it:

1. The catalogue: the real values of every small dimension, read once through the normal
   compiler and runner (so as `adaa_query`, and only values a query can actually match),
   then listed in the agent prompt.
2. check_filters(): after the form is filled, every filter value is checked against the
   catalogue. A close value is replaced and noted; an unknown value stops with a plain
   message that lists the closest real values.
"""

import difflib
import re
import unicodedata
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from adaa.semantic_layer.definitions import SemanticLayer
from adaa.semantic_layer.request import FilterValue, StructuredRequest
from adaa.semantic_layer.runner import QueryResult

MAX_VALUES = 100  # bigger dimensions (seller IDs) stay out of the prompt and the check


class ValueNotFoundError(Exception):
    """A filter value is not in the data; the message names the closest real values."""


class ValueCatalogue(BaseModel):
    model_config = ConfigDict(frozen=True)

    values: dict[str, list[FilterValue]]  # dimension name → its real values
    labels: dict[str, dict[str, str]] = {}  # dimension → stored code → name (value_labels)

    def shown(self, dimension: str, value: FilterValue) -> str:
        """How a value appears in the prompt: 'SP (São Paulo)' when it has a name."""
        name = self.labels.get(dimension, {}).get(str(value))
        return f"{value} ({name})" if name else str(value)

    def prompt_text(self) -> str:
        return "\n".join(
            f"- `{dim}`: {', '.join(self.shown(dim, v) for v in values)}"
            for dim, values in self.values.items()
        )


def build_catalogue(
    layer: SemanticLayer, ask: Callable[[StructuredRequest], QueryResult]
) -> ValueCatalogue:
    """Read each dimension's values with a breakdown query; keep the small dimensions.

    `ask` runs one form (the real runner, or a fake in tests). Each dimension is paired
    with the first metric the grain rule allows, so the query never double counts.
    """
    found: dict[str, list[FilterValue]] = {}
    for name in layer.dimensions:
        if layer.dimensions[name].kind == "time":  # dates: the form's `period` handles them
            continue
        metric = next(m for m in layer.metrics if layer.can_use(m, name))
        result = ask(StructuredRequest(metric=metric, dimensions=[name], limit=MAX_VALUES + 1))
        if result.row_count <= MAX_VALUES:
            values = [as_value(row[0]) for row in result.rows if row[0] is not None]
            found[name] = sorted(values, key=str)
    labels = {name: d.value_labels for name, d in layer.dimensions.items() if d.value_labels}
    return ValueCatalogue(values=found, labels=labels)


def as_value(cell: object) -> FilterValue:
    return cell if isinstance(cell, str | int | float) else str(cell)


def normal(value: FilterValue) -> str:
    """Loose form for matching: no accents, lower case, spaces and hyphens as _, no plural s."""
    plain = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    text = re.sub(r"[\s\-]+", "_", plain.strip().lower())
    return text[:-1] if text.endswith("s") and len(text) > 3 else text


def check_filters(
    form: StructuredRequest, catalogue: ValueCatalogue
) -> tuple[StructuredRequest, list[str]]:
    """The form with every filter value matched to a real value, plus notes for "how".

    Raises ValueNotFoundError for a value with no close match.
    """
    notes: list[str] = []
    filters = []
    for f in form.filters:
        real = catalogue.values.get(f.dimension)
        if real is None:  # not catalogued (e.g. seller IDs): nothing to check against
            filters.append(f)
            continue
        by_normal = {normal(v): v for v in real}
        names = catalogue.labels.get(f.dimension, {})
        by_normal |= {normal(name): code for code, name in names.items() if code in real}
        matched: list[FilterValue] = []
        for value in f.values:
            if value in real:
                matched.append(value)
            elif normal(value) in by_normal:
                fixed = by_normal[normal(value)]
                matched.append(fixed)
                if str(value) != str(fixed):  # "5" for 5 is the same value, no note
                    notes.append(f"I read '{value}' as '{fixed}'.")
            else:
                shown = [catalogue.shown(f.dimension, v) for v in real]
                close = difflib.get_close_matches(str(value), shown, n=3)
                hint = f" Did you mean: {', '.join(close)}?" if close else ""
                raise ValueNotFoundError(f"No {f.dimension} called '{value}' in the data.{hint}")
        filters.append(f.model_copy(update={"values": matched}))
    return form.model_copy(update={"filters": filters}), notes
