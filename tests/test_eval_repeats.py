"""Offline tests for B3a: --ids selection and --repeats in both eval runners.

The pipeline is faked (it returns the ground-truth table), so no LLM is called.
"""

import pytest

import eval.run_eval as run_eval_mod
import eval.run_multiturn_eval as mt_mod
from eval.metrics import is_answer_fallback, llm_usage_summary

CALLS = [
    {"name": "planner", "model": "openai/gpt-oss-20b", "input_tokens": 2000, "output_tokens": 100,
     "total_tokens": 2100, "latency_s": 1.0, "error": None},
    {"name": "answer_gen", "model": "openai/gpt-oss-20b", "input_tokens": 300, "output_tokens": 80,
     "total_tokens": 380, "latency_s": 0.5, "error": None},
]


def fresh_calls():
    return [dict(c) for c in CALLS]


# ---------------------------------------------------------------- single-turn runner
@pytest.fixture
def faked_single(monkeypatch):
    df = run_eval_mod._load_dataset()
    gt_by_query = {c.query: c.ground_truth_fn(df) for c in run_eval_mod.select_cases(["Q01", "Q36"])}
    seen = []

    def fake_pipeline(query):
        seen.append(query)
        return {"status": "success", "final_df": gt_by_query[query], "plan": [], "trace": [],
                "total_executions": 1, "answer": "ok", "llm_calls": fresh_calls(), "events": []}

    monkeypatch.setattr(run_eval_mod, "run_pipeline", fake_pipeline)
    return seen


def test_select_cases_keeps_order_and_spans_rounds():
    ids = [c.id for c in run_eval_mod.select_cases(["Q36", "Q01", "Q43"])]  # rounds 2, 1, 3
    assert ids == ["Q36", "Q01", "Q43"]


def test_select_cases_rejects_unknown_ids():
    with pytest.raises(ValueError, match="Q99"):
        run_eval_mod.select_cases(["Q01", "Q99"])


def test_repeats_run_every_case_each_round(faked_single):
    cases = run_eval_mod.select_cases(["Q01", "Q36"])
    records = run_eval_mod.run_eval(verbose=False, cases=cases, repeats=3)
    assert [(r["id"], r["repeat"]) for r in records] == [
        ("Q01", 1), ("Q36", 1), ("Q01", 2), ("Q36", 2), ("Q01", 3), ("Q36", 3)]
    assert len(faked_single) == 6                    # pipeline really called 6 times
    assert all(r["value_match"] for r in records)    # the fake returns the ground truth
    assert all(r["llm_call_count"] == 2 and r["input_tokens"] == 2300 for r in records)


def test_default_is_a_single_run_marked_repeat_1(faked_single):
    records = run_eval_mod.run_eval(verbose=False, cases=run_eval_mod.select_cases(["Q01"]))
    assert len(records) == 1 and records[0]["repeat"] == 1


# ---------------------------------------------------------------- multi-turn runner
@pytest.fixture
def faked_multi(monkeypatch):
    df = mt_mod._load_dataset()
    case = next(c for c in mt_mod.MULTITURN_TEST_CASES if c.id == "MT03")
    final_q = case.turns[-1].query
    gt = case.turns[-1].ground_truth_fn(df)
    log = []  # (query, session_id)

    def fake_pipeline(query, session_id=None):
        log.append((query, session_id))
        return {"status": "success", "final_df": gt, "plan": [], "answer": "ok",
                "llm_calls": fresh_calls()}

    monkeypatch.setattr(mt_mod, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(mt_mod.time, "sleep", lambda s: pytest.fail("sleep must not run with turn_delay=0"))
    return log, final_q


def test_multiturn_repeats_use_fresh_sessions_and_sum_llm_calls(faked_multi):
    log, _ = faked_multi
    records = mt_mod.run_multiturn_eval(verbose=False, ids=["MT03"], repeats=2, turn_delay=0)
    assert [r["repeat"] for r in records] == [1, 2]
    assert all(r["outcome"] == "pass" for r in records)

    # Each repeat: both turns share one session; the two repeats use different sessions.
    sessions = [s for _, s in log]
    assert sessions[0] == sessions[1] and sessions[2] == sessions[3]
    assert sessions[0] != sessions[2]
    assert records[0]["session_id"] != records[1]["session_id"]

    # Usage is summed over every turn of the case (2 turns x 2 calls)
    r = records[0]
    assert r["llm_call_count"] == 4 and r["input_tokens"] == 4600
    assert r["answer_check"] in ("pass", "no_numbers", "n/a") and r["answer"] == "ok"


def test_multiturn_rejects_unknown_ids(faked_multi):
    with pytest.raises(ValueError, match="MT99"):
        mt_mod.run_multiturn_eval(verbose=False, ids=["MT03", "MT99"], turn_delay=0)


# ---------------------------------------------------------------- shared helpers
def test_llm_usage_summary_and_fallback_detection():
    calls = fresh_calls()
    u = llm_usage_summary(calls)
    assert (u["llm_call_count"], u["input_tokens"], u["output_tokens"]) == (2, 2300, 180)
    assert calls[0]["cost_usd"] > 0 and u["cost_all_prices_verified"] is True

    assert is_answer_fallback(fresh_calls()) is False
    failed = fresh_calls()
    failed[1]["error"] = "NotFoundError"
    assert is_answer_fallback(failed) is True
    assert is_answer_fallback([]) is False           # no call log (old runs): assume LLM answer


def test_refusal_is_not_a_fallback_answer():
    planner_only = [dict(CALLS[0])]                      # planner refused: the answer step never ran
    assert is_answer_fallback(planner_only) is False
    attempted_but_failed = planner_only + [dict(CALLS[1], error="NotFoundError", total_tokens=None)]
    assert is_answer_fallback(attempted_but_failed) is True


def test_a_skipped_multiturn_case_still_carries_its_token_and_cost_totals(monkeypatch):
    """A context turn that errors skips the case; its LLM calls were still paid for and must be counted."""
    def failing_pipeline(query, session_id=None):
        return {"status": "error", "message": "boom", "final_df": None, "plan": [], "llm_calls": fresh_calls()}

    monkeypatch.setattr(mt_mod, "run_pipeline", failing_pipeline)
    (rec,) = mt_mod.run_multiturn_eval(verbose=False, ids=["MT03"], turn_delay=0)
    assert rec["outcome"] == "skipped"
    assert rec["input_tokens"] == 2300 and rec["output_tokens"] == 180 and rec["cost_usd"] > 0
