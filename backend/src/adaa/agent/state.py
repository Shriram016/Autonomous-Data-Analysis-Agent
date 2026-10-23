"""The shapes the agent graph uses (§0 M1.3, step 6).

AgentState is the shared notebook the three nodes pass along (understand → query → answer):
each node reads it and returns only the fields it fills; LangGraph merges them in. It lives
in the worker's memory for one question and is then thrown away (checkpoints in Postgres
come later, ADR 0011).

FinishedAnswer is what the caller gets: the API (M1.5) and the page (M1.6) use it, and later
it becomes a row in the database. It is a Pydantic model, so it turns into JSON and back.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from adaa.agent.facts import Facts
from adaa.llm.types import Usage
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import QueryResult

# Why a question failed. Used for logs, and later by the clarify and refuse routes.
ErrorKind = Literal[
    "llm_unavailable",  # the LLM provider could not answer (outage, timeout, no key)
    "llm_output",  # the LLM's form did not match, even after the retry
    "value_not_found",  # a filter value is not in the data ("Paris")
    "compile_refused",  # the semantic layer can't answer the form (double count, ...)
    "query_timeout",  # the query took longer than the 5 s limit
    "data_unavailable",  # the database could not be reached
    "job_timeout",  # the whole question passed the worker's soft time limit (M1.4)
]


class AgentError(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: ErrorKind
    message: str  # plain and safe to show the manager


NO_USAGE = Usage(input_tokens=0, output_tokens=0, thinking_tokens=0, cost_usd=0.0)


class AgentState(BaseModel):
    """Everything a question collects on its way through the graph.

    A Pydantic model, not a plain dict: when checkpoints arrive (ADR 0011), a state saved by
    one version of the code may be loaded by a newer one, and Pydantic checks it on load,
    so a mismatch is a clear error at once instead of a hidden bug in a later node.
    Every field but `question` has a default, so the caller starts with only the question.
    """

    model_config = ConfigDict(extra="forbid")  # a misspelt field is an error, not ignored

    state_version: int = 1  # raise when a field changes meaning; a migration can check it
    question: str  # set by the caller
    form: StructuredRequest | None = None  # understand
    value_notes: list[str] = []  # understand: "I read 'toy' as 'toys'."
    result: QueryResult | None = None  # query
    facts: Facts | None = None  # answer
    answer_text: str | None = None  # answer: the LLM sentence, or the template
    used_template: bool = False  # answer: True when the LLM or the guardrail failed
    usage: Usage = NO_USAGE  # every LLM call adds to it
    error: AgentError | None = None  # any node; the graph stops when it is set


class Table(BaseModel):
    model_config = ConfigDict(frozen=True)

    headers: list[str]
    rows: list[list[str]]  # every row, formatted (the answer LLM saw at most max_rows)


class Versions(BaseModel):
    """What produced the answer: 'version (first 12 characters of the fingerprint)'."""

    model_config = ConfigDict(frozen=True)

    semantic_layer: str
    agent_prompt: str
    answer_prompt: str


class FinishedAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    status: Literal["answered", "failed"]
    text: str  # the answer, or the plain error message
    error_kind: ErrorKind | None = None
    table: Table | None = None
    how: list[str] = []  # "how I got this" + value notes + "Data as of ..."
    used_template: bool = False
    versions: Versions
    usage: Usage  # every LLM call of this question added together
