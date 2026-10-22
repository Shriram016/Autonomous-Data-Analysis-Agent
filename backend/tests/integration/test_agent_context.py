"""The real start-up context (needs docker compose up + data loaded)."""

from datetime import date

import pytest

from adaa.agent.context import load_context

pytestmark = pytest.mark.integration


def test_real_context() -> None:
    context = load_context()
    assert context.data_date == date(2018, 8, 31)
    assert "toys" in context.agent_prompt.text
    assert "SP (São Paulo)" in context.agent_prompt.text
    assert context.adapter is None  # the real adapter comes from config/llm.yaml
