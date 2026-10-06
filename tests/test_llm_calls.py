"""Offline tests for B1c: per-run LLM call log, and cost in the eval record."""

import pytest

from eval.metrics import compute_record
from eval.pricing import call_cost
from eval.test_cases import EvalCase
from src.utils.langfuse_helper import llm_generation, pop_llm_calls


def gen(run_id, name="planner", model="openai/gpt-oss-20b"):
    return llm_generation(name=name, model=model, model_params={}, input_messages=[],
                          run_id=run_id, session_id=None)


def test_successful_call_records_tokens_and_latency():
    with gen("r1") as g:
        g.output("x")
        g.usage(100, 20, 120)
    calls = pop_llm_calls("r1")
    assert len(calls) == 1
    c = calls[0]
    assert (c["name"], c["input_tokens"], c["output_tokens"], c["total_tokens"]) == ("planner", 100, 20, 120)
    assert c["latency_s"] >= 0 and c["error"] is None


def test_exception_inside_call_is_recorded_and_reraised():
    with pytest.raises(TimeoutError):
        with gen("r2"):
            raise TimeoutError("slow")
    (c,) = pop_llm_calls("r2")
    assert c["input_tokens"] is None and "TimeoutError" in c["error"]


def test_gen_error_message_is_recorded():
    with gen("r3") as g:
        g.usage(5, 1, 6)
        g.error("Pydantic validation failed")
    (c,) = pop_llm_calls("r3")
    assert c["error"] == "Pydantic validation failed" and c["total_tokens"] == 6


def test_calls_are_ordered_isolated_per_run_and_cleared_on_pop():
    with gen("a", name="planner") as g:
        g.usage(1, 1, 2)
    with gen("b", name="answer_gen") as g:
        g.usage(2, 2, 4)
    with gen("a", name="answer_gen") as g:
        g.usage(3, 3, 6)
    assert [c["name"] for c in pop_llm_calls("a")] == ["planner", "answer_gen"]
    assert [c["name"] for c in pop_llm_calls("b")] == ["answer_gen"]
    assert pop_llm_calls("a") == []


def test_call_cost_math_and_edge_cases():
    cost, verified = call_cost("openai/gpt-oss-20b", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.075 + 0.30) and verified is True
    assert call_cost("llama-3.1-8b-instant", 1000, 100)[1] is False  # unverified price
    assert call_cost("openai/gpt-oss-20b", None, None) == (0.0, True)  # failed attempt
    assert call_cost("mystery-model", 10, 10) == (0.0, False)


def test_eval_record_sums_tokens_latency_and_cost(df):
    calls = [
        {"name": "planner", "model": "openai/gpt-oss-20b", "input_tokens": 2000,
         "output_tokens": 500, "latency_s": 1.5, "error": None},
        {"name": "planner", "model": "openai/gpt-oss-20b", "input_tokens": None,
         "output_tokens": None, "latency_s": 30.0, "error": "APITimeoutError"},
        {"name": "answer_gen", "model": "llama-3.1-8b-instant", "input_tokens": 300,
         "output_tokens": 60, "latency_s": 0.5, "error": None},
    ]
    case = EvalCase(id="T", query="q", ground_truth_fn=None, compare_mode="value_only")
    rec = compute_record(case=case, gt_df=None, gt_error=False,
                         pipeline_result={"status": "success", "final_df": df, "llm_calls": calls},
                         compare_result=None, duration_s=0.0)
    assert rec["llm_call_count"] == 3
    assert (rec["input_tokens"], rec["output_tokens"]) == (2300, 560)
    assert rec["llm_latency_s"] == 32.0
    expected = (2000 * 0.075 + 500 * 0.30) / 1e6 + (300 * 0.05 + 60 * 0.08) / 1e6
    assert rec["cost_usd"] == pytest.approx(expected, abs=1e-6)
    assert rec["cost_all_prices_verified"] is False  # llama price is unverified


def test_eval_record_without_llm_calls_is_zero(df):
    case = EvalCase(id="T", query="q", ground_truth_fn=None, compare_mode="value_only")
    rec = compute_record(case=case, gt_df=None, gt_error=False,
                         pipeline_result={"status": "error"}, compare_result=None, duration_s=0.0)
    assert (rec["llm_call_count"], rec["input_tokens"], rec["cost_usd"]) == (0, 0, 0.0)
