"""Load and check the eval cases (eval/questions/cases.yaml, §0 M1.7).

A case is a question plus EITHER the expected form (the right plan) and the hand-written
expected SQL (the right answer, independent of our compiler), OR the expected error (a
question that must stop). The file refuses to load if two cases share an id or a case mixes
the two; check_cases() also proves every expected form compiles, so a typo in the file can't
quietly make a case unpassable.
"""

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from adaa.agent.state import ErrorKind
from adaa.semantic_layer.compiler import CompileError, compile_request
from adaa.semantic_layer.definitions import SemanticLayer
from adaa.semantic_layer.request import StructuredRequest
from adaa.settings import REPO_ROOT

CASES_FILE = REPO_ROOT / "eval" / "questions" / "cases.yaml"

CaseKind = Literal[
    "simple", "breakdown", "period", "filter", "status", "relative_date", "top", "must_stop"
]


class EvalCaseError(Exception):
    """The case file is wrong; the eval does not run."""


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: CaseKind
    question: str
    note: str | None = None
    expected_form: StructuredRequest | None = None  # the right plan (compared as a hint)
    expected_sql: str | None = None  # hand-written: the right answer, not via our compiler
    expected_error: ErrorKind | None = None  # a question that must stop

    @model_validator(mode="after")
    def one_kind_of_expectation(self) -> Self:
        answerable = self.expected_form is not None and self.expected_sql is not None
        stops = self.expected_error is not None
        partial = (self.expected_form is None) != (self.expected_sql is None)
        if partial or answerable == stops:
            raise ValueError(
                f"case '{self.id}' needs expected_form + expected_sql, or expected_error alone"
            )
        return self


class EvalSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    cases: list[EvalCase]

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        ids = [case.id for case in self.cases]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        if repeated:
            raise ValueError(f"case ids used twice: {repeated}")
        return self


def load_cases(path: Path = CASES_FILE) -> EvalSet:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        return EvalSet.model_validate(raw)
    except ValueError as e:
        raise EvalCaseError(f"Eval cases not loaded:\n{e}") from e


def check_cases(cases: EvalSet, layer: SemanticLayer) -> list[str]:
    """Problems with the expected forms (empty = every one compiles)."""
    problems = []
    for case in cases.cases:
        if case.expected_form is None:
            continue
        try:
            compile_request(case.expected_form, layer)
        except CompileError as e:
            problems.append(f"case '{case.id}': {e}")
    return problems
