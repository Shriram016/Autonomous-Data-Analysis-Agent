"""Offline tests for graph routing, the param fixer, the replanner and a
full graph run with every LLM-touching node replaced by a fake.

No network, no API keys: Groq calls are monkeypatched.
"""

import pandas as pd
import pytest
from langgraph.graph import END

import src.core.graph as graph_mod
import src.core.param_fixer as pf
import src.core.replanner as rp
from src.config import MAX_RETRIES_PER_STEP
from src.core.graph import (
    _route_after_execute_step,
    _route_after_planner,
    _route_after_replanner,
    _route_after_schema_gen,
    build_graph,
)
from src.core.planner import PlanResponse, PlanStep
from src.core.executor import _run_step


def S(n, tool, params, inp, out):
    return PlanStep(step=n, tool=tool, parameters=params, input=inp, output=out)


def state(**kw):
    base = dict(status="running", plan=[S(1, "top_n", {"N": 1}, "original_df", "a")] * 2,
                current_step_index=0, retry_count=0, total_executions=0, max_executions=4)
    base.update(kw)
    return base


# ---------------------------------------------------------------- pure routing functions
def test_route_after_schema_gen():
    assert _route_after_schema_gen({"status": "error"}) == END
    assert _route_after_schema_gen({"status": "running"}) == "planner"


@pytest.mark.parametrize("status,expected", [
    ("error", END), ("unsolvable", END), ("running", "execute_step")])
def test_route_after_planner(status, expected):
    assert _route_after_planner({"status": status}) == expected


def test_route_success_more_steps_loops():
    assert _route_after_execute_step(state(current_step_index=1)) == "execute_step"


def test_route_success_last_step_goes_to_answer():
    assert _route_after_execute_step(state(current_step_index=2)) == "answer_gen"


def test_route_failure_with_retries_left_goes_to_param_fixer():
    s = state(status="error", retry_count=0)
    assert _route_after_execute_step(s) == "param_fixer"


def test_route_failure_retries_exhausted_goes_to_replanner():
    s = state(status="error", retry_count=MAX_RETRIES_PER_STEP)
    assert _route_after_execute_step(s) == "replanner"


def test_route_execution_cap_ends_run_before_anything_else():
    s = state(status="error", retry_count=0, total_executions=4, max_executions=4)
    assert _route_after_execute_step(s) == END


@pytest.mark.parametrize("status,expected", [
    ("error", END), ("unsolvable", END), ("running", "execute_step")])
def test_route_after_replanner(status, expected):
    assert _route_after_replanner({"status": status}) == expected


# ---------------------------------------------------------------- param fixer (LLM mocked)
BAD_STEP = S(1, "sort", {"sort_col": {"Sales": "up"}}, "original_df", "out")


def fake_fix(responses):
    it = iter(responses)
    return lambda *a, **k: next(it)


def test_param_fixer_applies_valid_correction(monkeypatch):
    good = {"status": "success", "data": pf.ParamFixResponse(parameters={"sort_col": {"Sales": "asc"}})}
    monkeypatch.setattr(pf, "_call_groq", fake_fix([good]))
    fixed = pf.fix_params(BAD_STEP, {"message": "bad order"}, "q", {})
    assert fixed.parameters == {"sort_col": {"Sales": "asc"}}
    assert (fixed.step, fixed.tool, fixed.input, fixed.output) == (1, "sort", "original_df", "out")


def test_param_fixer_returns_original_when_llm_errors(monkeypatch):
    monkeypatch.setattr(pf, "_call_groq", fake_fix([{"status": "error", "message": "timeout"}]))
    assert pf.fix_params(BAD_STEP, {"message": "x"}, "q", {}) == BAD_STEP


def test_param_fixer_retries_once_then_gives_up_on_invalid_params(monkeypatch):
    invalid = {"status": "success", "data": pf.ParamFixResponse(parameters={"bogus": 1})}
    monkeypatch.setattr(pf, "_call_groq", fake_fix([invalid, invalid]))
    assert pf.fix_params(BAD_STEP, {"message": "x"}, "q", {}) == BAD_STEP


# ---------------------------------------------------------------- replanner (LLM mocked)
def ok_plan():
    return PlanResponse(status="success", plan=[S(1, "top_n", {"N": 1}, "original_df", "a")])


def test_replanner_returns_valid_plan(monkeypatch):
    monkeypatch.setattr(rp, "_call_groq", fake_fix([{"status": "success", "data": ok_plan()}]))
    r = rp.replan({}, {"failed_step": BAD_STEP, "message": "x", "trace": []}, "q", {})
    assert r["status"] == "success" and len(r["plan"]) == 1


def test_replanner_passes_through_unsolvable(monkeypatch):
    resp = PlanResponse(status="unsolvable", reason="no such column")
    monkeypatch.setattr(rp, "_call_groq", fake_fix([{"status": "success", "data": resp}]))
    r = rp.replan({}, {"failed_step": BAD_STEP, "message": "x", "trace": []}, "q", {})
    assert r == {"status": "unsolvable", "message": "no such column"}


def test_replanner_rejects_invalid_plan_after_one_retry(monkeypatch):
    broken = PlanResponse(status="success", plan=[S(1, "nope", {}, "original_df", "a")])
    monkeypatch.setattr(rp, "_call_groq", fake_fix([{"status": "success", "data": broken}] * 2))
    r = rp.replan({}, {"failed_step": BAD_STEP, "message": "x", "trace": []}, "q", {})
    assert r["status"] == "error"


# ---------------------------------------------------------------- executor + critic wiring
def test_run_step_reports_critic_failure_as_error(df):
    # top_n succeeds, but we force the critic to see too many rows via a monkeypatched tool
    import src.core.executor as ex
    step = S(1, "top_n", {"N": 1}, "original_df", "a")
    orig = ex.TOOL_REGISTRY["top_n"]
    ex.TOOL_REGISTRY["top_n"] = lambda df, N: {"status": "success", "message": "", "result": df}
    try:
        r = _run_step(step, {"original_df": df})
    finally:
        ex.TOOL_REGISTRY["top_n"] = orig
    assert r["status"] == "error" and "Critic failed" in r["message"]


def test_run_step_missing_input_key():
    r = _run_step(S(1, "top_n", {"N": 1}, "nope", "a"), {"original_df": pd.DataFrame({"a": [1]})})
    assert r["status"] == "error" and "not found" in r["message"]


# ---------------------------------------------------------------- full graph, fake nodes
def make_state(df, plan):
    return {
        "query": "q", "run_id": "t", "session_id": "t", "original_df": df,
        "recent_questions": [], "schema": {}, "plan": plan,
        "max_executions": len(plan) * 2, "state_store": {"original_df": df},
        "current_step_index": 0, "retry_count": 0, "total_executions": 0,
        "trace": [], "final_df": None, "status": "running", "message": "", "answer": None,
    }


@pytest.fixture
def graph(monkeypatch, tmp_path):
    monkeypatch.setattr(graph_mod, "CHECKPOINT_DB_PATH", str(tmp_path / "cp.sqlite"))
    # Entry nodes and answer node are LLM-backed: replace with pass-throughs.
    monkeypatch.setattr(graph_mod, "schema_gen_node", lambda s: {"schema": {}})
    monkeypatch.setattr(graph_mod, "planner_node", lambda s: {})
    monkeypatch.setattr(graph_mod, "answer_gen_node", lambda s: {"answer": "done"})
    with build_graph() as g:
        yield g


def invoke(g, st):
    return g.invoke(st, config={"configurable": {"thread_id": "t"}})


def test_graph_happy_path_runs_to_answer(graph, df):
    plan = [S(1, "sort", {"sort_col": {"Sales": "desc"}}, "original_df", "s"),
            S(2, "top_n", {"N": 2}, "s", "t")]
    out = invoke(graph, make_state(df, plan))
    assert out["status"] == "running" and out["answer"] == "done"
    assert list(out["final_df"]["Sales"]) == [200.0, 100.0]
    assert out["total_executions"] == 2


def test_graph_param_fixer_repairs_a_failing_step(graph, df, monkeypatch):
    def fixer(s):
        plan = list(s["plan"])
        plan[s["current_step_index"]] = S(1, "sort", {"sort_col": {"Sales": "asc"}}, "original_df", "s")
        return {"plan": plan, "retry_count": s["retry_count"] + 1, "status": "running", "message": ""}

    monkeypatch.setattr(graph_mod, "param_fixer_node", fixer)
    with build_graph() as g:  # rebuild so the patched node is wired in
        plan = [S(1, "sort", {"sort_col": {"Sales": "up"}}, "original_df", "s")]
        out = invoke(g, make_state(df, plan))
    assert out["answer"] == "done"
    assert out["total_executions"] == 2  # one failure + one fixed retry


def test_graph_replans_after_retries_exhausted(graph, df, monkeypatch):
    new_plan = [S(1, "sort", {"sort_col": {"Sales": "asc"}}, "original_df", "s")]

    monkeypatch.setattr(graph_mod, "param_fixer_node",
                        lambda s: {"retry_count": s["retry_count"] + 1, "status": "running", "message": ""})
    monkeypatch.setattr(graph_mod, "replanner_node", lambda s: {
        "plan": new_plan, "max_executions": 10, "current_step_index": 0, "retry_count": 0,
        "state_store": {"original_df": s["original_df"]}, "status": "running", "message": ""})
    with build_graph() as g:
        bad = [S(1, "sort", {"sort_col": {"Sales": "up"}}, "original_df", "s")]
        st = make_state(df, bad)
        st["max_executions"] = 10
        out = invoke(g, st)
    assert out["answer"] == "done"
    # 1 original + MAX_RETRIES_PER_STEP retries failed, then 1 success after replan
    assert out["total_executions"] == 1 + MAX_RETRIES_PER_STEP + 1


def test_graph_stops_at_execution_cap(graph, df, monkeypatch):
    monkeypatch.setattr(graph_mod, "param_fixer_node",
                        lambda s: {"retry_count": s["retry_count"] + 1, "status": "running", "message": ""})
    with build_graph() as g:
        bad = [S(1, "sort", {"sort_col": {"Sales": "up"}}, "original_df", "s")]
        st = make_state(df, bad)
        st["max_executions"] = 2
        out = invoke(g, st)
    assert out["status"] == "error" and out["answer"] is None
    assert out["total_executions"] == 2
