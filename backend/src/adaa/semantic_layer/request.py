"""The structured request: the form the LLM fills in instead of writing SQL (ADR 0003).

This module checks only that the form is filled in correctly: required fields, allowed
operators, sensible limits. Whether a metric exists, or whether a dimension is allowed for it
(the grain rule), needs the semantic layer, so the compiler checks that (compiler.py).

The same model is the LLM's output schema in M1.3 (structured output), so one definition
serves both the LLM and the compiler. `extra="forbid"`: the LLM cannot add unknown fields.
"""

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_DIMENSIONS = 2
MAX_LIMIT = 1000  # rows; locked in the failure design (results capped, summary for the LLM)

FilterValue = str | int | float


class Filter(BaseModel):
    """Keep only rows where `dimension` `op` `values`, e.g. product_category in [toys, books]."""

    model_config = ConfigDict(extra="forbid")

    dimension: str = Field(min_length=1)
    op: Literal["=", "!=", "in", "not in"]
    values: list[FilterValue] = Field(min_length=1)

    @model_validator(mode="after")
    def single_value_for_equals(self) -> Self:
        if self.op in ("=", "!=") and len(self.values) != 1:
            raise ValueError(f"operator '{self.op}' needs exactly one value; use 'in' for several")
        return self


class Period(BaseModel):
    """Order purchase dates from `start` to `end`, both days included."""

    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def start_before_end(self) -> Self:
        if self.start > self.end:
            raise ValueError(f"period start {self.start} is after end {self.end}")
        return self


class Sort(BaseModel):
    """Order the rows by the metric or by one of the request's dimensions."""

    model_config = ConfigDict(extra="forbid")

    by: str = Field(min_length=1)
    direction: Literal["asc", "desc"] = "desc"


class StructuredRequest(BaseModel):
    """One numbers question as a form: which metric, broken down how, for which rows."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(min_length=1)
    dimensions: list[str] = Field(default_factory=list, max_length=MAX_DIMENSIONS)
    filters: list[Filter] = Field(default_factory=list)
    period: Period | None = None  # None → the semantic layer's default period
    sort: Sort | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)

    @model_validator(mode="after")
    def no_repeated_dimension(self) -> Self:
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError(f"a dimension is repeated: {self.dimensions}")
        return self
