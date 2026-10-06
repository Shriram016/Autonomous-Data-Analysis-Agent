"""Offline tests for B1b: param-fixer / replanner events and the eval counts.

The real param_fixer_node / replanner_node run; only the Groq calls are faked.
"""

import pytest

import src.core.graph as graph_mod
import src.core.param_fixer as pf
import src.core.replanner as rp
from eval.metrics import compute_record
from eval.test_cases import EvalCase
from src.core.graph import build_graph
from src.core.planner import PlanResponse
from tests.test_graph_routing import S, make_state, invoke

BAD = [S(1, "sort", {"sort_col": {"Sales": "up"}}, "original_df", "s")]
GOOD_PARAMS = {"sort_col": {"Sales": "asc"}}


def fix_resp(params):
    return {"status": "success", "data": pf.ParamFixResponse(parameters=params)}


def replan_resp(plan):
    return {"status": "success", "data": PlanResponse(status="success", plan=plan)}


@pytest.fixture
def run_graph(monkeypatch, tmp_path):
    """Graph with real fixer/replanner nodes; LLM-backed entry/answer nodes stubbed."""
    monkeypatch.setattr(graph_mod, "CHECKPOINT_DB_PATH", str(tmp_path / "cp.sqlite"))
    monkeypatch.setattr(graph_mod, "schema_gen_node", lambda s: {"schema": {}})
    monkeypatch.setattr(graph_mod, "planner_node", lambda s: {})
    monkeypatch.setattr(graph_mod, "answer_gen_node", lambda s: {"answer": "done"})

    def run(df, fixer_responses, replanner_responses=()):
        f, r = iter(fixer_responses), iter(replanner_responses)
        monkeypatch.setattr(pf, "_call_groq", lambda *a, **k: next(f))
        monkeypatch.setattr(rp, "_call_groq", lambda *a, **k: next(r))
        st = make_state(df, BAD)
        st["events"] = []
        st["max_executions"] = 10
        with build_graph() as g:
            return invoke(g, st)

    return run


def test_effective_param_fix_is_recorded(run_graph, df):
    out = run_graph(df, [fix_resp(GOOD_PARAMS)])
    assert out["answer"] == "done"
    assert len(out["events"]) == 1
    e = out["events"][0]
    assert e["type"] == "param_fix" and e["changed"] is True
    assert e["old_parameters"] == {"sort_col": {"Sales": "up"}}
    assert e["new_parameters"] == GOOD_PARAMS
    assert e["trigger_message"]  # the tool error that triggered the fix


def test_ineffective_fixes_then_replan_are_all_recorded(run_graph, df):
    # Fixer LLM errors twice (params unchanged), then the replanner rescues the run.
    err = {"status": "error", "message": "timeout"}
    good_plan = [S(1, "sort", GOOD_PARAMS, "original_df", "s")]
    out = run_graph(df, [err, err], [replan_resp(good_plan)])
    assert out["answer"] == "done"
    types = [e["type"] for e in out["events"]]
    assert types == ["param_fix", "param_fix", "replan"]
    assert [e["changed"] for e in out["events"][:2]] == [False, False]
    replan = out["events"][2]
    assert replan["result"] == "success"
    assert replan["old_plan"][0]["parameters"] == {"sort_col": {"Sales": "up"}}  # old plan preserved
    assert replan["new_plan"][0]["parameters"] == GOOD_PARAMS


def test_unsolvable_replan_is_recorded(run_graph, df):
    err = {"status": "error", "message": "timeout"}
    unsolv = {"status": "success", "data": PlanResponse(status="unsolvable", reason="nope")}
    out = run_graph(df, [err, err], [unsolv])
    assert out["status"] == "unsolvable"
    replan = out["events"][-1]
    assert replan["type"] == "replan" and replan["result"] == "unsolvable"
    assert replan["new_plan"] is None


def test_eval_record_counts_events(df):
    events = [
        {"type": "param_fix", "changed": False},
        {"type": "param_fix", "changed": True},
        {"type": "replan", "result": "success"},
    ]
    case = EvalCase(id="T", query="q", ground_truth_fn=None, compare_mode="value_only")
    rec = compute_record(
        case=case, gt_df=None, gt_error=False,
        pipeline_result={"status": "success", "plan": [], "trace": [], "events": events,
                         "total_executions": 0, "final_df": df, "answer": None},
        compare_result=None, duration_s=0.0,
    )
    assert rec["param_fix_count"] == 2
    assert rec["param_fix_effective_count"] == 1
    assert rec["replan_count"] == 1
    assert rec["events"] == events


def test_eval_record_without_events_defaults_to_zero(df):
    case = EvalCase(id="T", query="q", ground_truth_fn=None, compare_mode="value_only")
    rec = compute_record(case=case, gt_df=None, gt_error=False,
                         pipeline_result={"status": "success", "final_df": df},
                         compare_result=None, duration_s=0.0)
    assert (rec["param_fix_count"], rec["param_fix_effective_count"], rec["replan_count"]) == (0, 0, 0)
