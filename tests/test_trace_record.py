"""Offline tests for the B1a instrumentation: the critic check name lands in the
trace record, and the eval record keeps the plan and trace as JSON-safe data."""

import json

import pandas as pd

from eval.metrics import compute_record
from eval.test_cases import EvalCase
from src.core.executor import _run_step
from src.core.planner import PlanStep


def S(tool, params):
    return PlanStep(step=1, tool=tool, parameters=params, input="original_df", output="out")


def test_trace_records_which_critic_check_fired(df, monkeypatch):
    import src.core.executor as ex
    # Tool "succeeds" but returns too many rows -> top_n_rows check must fire
    monkeypatch.setitem(ex.TOOL_REGISTRY, "top_n",
                        lambda df, N: {"status": "success", "message": "", "result": df})
    r = _run_step(S("top_n", {"N": 1}), {"original_df": df})
    rec = r["trace_record"]
    assert r["status"] == "error"
    assert rec["critic"] == "fail"
    assert rec["critic_check"] == "top_n_rows"
    assert "N=1" in rec["critic_reason"]


def test_trace_critic_fields_are_none_on_pass(df):
    r = _run_step(S("top_n", {"N": 2}), {"original_df": df})
    rec = r["trace_record"]
    assert rec["critic"] == "pass"
    assert rec["critic_check"] is None and rec["critic_reason"] is None


def test_eval_record_keeps_plan_and_trace_json_safe(df):
    step = S("top_n", {"N": 2})
    trace = [_run_step(step, {"original_df": df})["trace_record"]]
    case = EvalCase(id="T1", query="q", ground_truth_fn=None, compare_mode="value_only")
    rec = compute_record(
        case=case, gt_df=None, gt_error=False,
        pipeline_result={"status": "success", "plan": [step], "trace": trace,
                         "total_executions": 1, "final_df": df.head(2), "answer": "a"},
        compare_result=None, duration_s=0.1,
    )
    assert rec["plan"] == [step.model_dump()]
    assert rec["trace"][0]["critic_check"] is None
    json.dumps(rec, default=str)  # must not raise
