from dataclasses import replace
from decimal import Decimal

import pytest

from adaa.agent.nodes import query
from adaa.agent.state import AgentState
from adaa.semantic_layer.compiler import CompileError
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import (
    TIMEOUT_MESSAGE,
    UNAVAILABLE_MESSAGE,
    DataUnavailableError,
    QueryResult,
    QueryTimeoutError,
)
from tests.unit.fakes import fake_context, query_result

STATE = AgentState(question="Total revenue", form=StructuredRequest(metric="revenue"))


def test_rows_come_back() -> None:
    context, _ = fake_context()
    rows = query_result((Decimal("13221498.11"),))
    update = query(STATE, replace(context, ask=lambda form: rows))
    assert update == {"result": rows}


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (CompileError("Revenue can't be split by payment type."), "compile_refused"),
        (QueryTimeoutError(TIMEOUT_MESSAGE), "query_timeout"),
        (DataUnavailableError(UNAVAILABLE_MESSAGE), "data_unavailable"),
    ],
)
def test_each_failure_becomes_a_plain_error(error: Exception, kind: str) -> None:
    def failing_ask(form: StructuredRequest) -> QueryResult:
        raise error

    context, _ = fake_context()
    update = query(STATE, replace(context, ask=failing_ask))
    assert update["error"].kind == kind
    assert update["error"].message == str(error)
