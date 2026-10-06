"""Offline tests for the answer generator after the move to gpt-oss-20b (M4)."""

from types import SimpleNamespace

import pandas as pd
import pytest

import src.core.answer_generator as ag
from src.config import ANSWER_MODEL
from src.utils.langfuse_helper import pop_llm_calls

TABLE = pd.DataFrame({"Sales_sum": [2297200.8603]})


def fake_client(content, finish_reason="stop", calls=None):
    def create(**kw):
        if calls is not None:
            calls.append(kw)
        msg = SimpleNamespace(content=content)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason=finish_reason)],
            usage=SimpleNamespace(prompt_tokens=230, completion_tokens=120, total_tokens=350),
        )
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.fixture
def patch_groq(monkeypatch):
    def apply(content, finish_reason="stop", calls=None):
        monkeypatch.setattr(ag, "GROQ_API_KEY", "test-key")
        monkeypatch.setattr(ag, "Groq", lambda api_key: fake_client(content, finish_reason, calls))
    return apply


def test_answer_model_is_gpt_oss_20b():
    assert ANSWER_MODEL == "openai/gpt-oss-20b"


def test_success_uses_configured_model_and_safe_params(patch_groq):
    calls = []
    patch_groq("  Total sales were $2,297,200.86.  ", calls=calls)
    r = ag.generate_answer("total sales?", TABLE, run_id="m4-ok")
    assert r == {"status": "success", "answer": "Total sales were $2,297,200.86."}
    sent = calls[0]
    assert sent["model"] == ANSWER_MODEL
    assert sent["max_tokens"] >= 1024          # reasoning tokens count toward the cap
    assert sent["reasoning_effort"] == "low"
    (rec,) = pop_llm_calls("m4-ok")
    assert rec["name"] == "answer_gen" and rec["error"] is None and rec["total_tokens"] == 350


@pytest.mark.parametrize("content", ["", "   ", None])
def test_empty_answer_is_an_error_not_a_blank_success(patch_groq, content):
    patch_groq(content, finish_reason="length")
    r = ag.generate_answer("total sales?", TABLE, run_id="m4-empty")
    assert r["status"] == "error" and "empty" in r["message"].lower()
    assert "length" in r["message"]            # finish_reason is surfaced for diagnosis
    (rec,) = pop_llm_calls("m4-empty")
    assert "Empty answer" in rec["error"]      # recorded as a failed attempt (B1c log)


def test_node_falls_back_when_answer_is_empty(patch_groq):
    from src.core.nodes import answer_gen_node
    patch_groq("", finish_reason="length")
    out = answer_gen_node({"run_id": "m4-node", "query": "q", "final_df": TABLE, "session_id": "s"})
    assert out["answer"] == "Sales_sum: 2297200.8603"   # deterministic fallback, never blank
