"""Offline tests for B3b: the stability report (eval/stability.py), using made-up records."""

import json

import pytest

from eval.stability import compute_stability, load_records, main, render_report

PLAN_A = [{"step": 1, "tool": "aggregate_column", "input": "original_df", "output": "step_1_output",
           "parameters": {"col_name": "Sales", "operation": "sum", "new_col_name": "Sales_sum"}}]
PLAN_B = [{"step": 1, "tool": "aggregate_column", "input": "original_df", "output": "step_1_output",
           "parameters": {"col_name": "Sales", "operation": "mean", "new_col_name": "Sales_mean"}}]


def rec(qid, repeat, passed=True, plan=PLAN_A, table=((100.0,),), answer="Total is $100.00.",
        mismatches=None, llm_errors=(), **extra):
    r = {
        "id": qid, "repeat": repeat, "value_match": passed, "gt_error": False,
        "pipeline_message": "", "mismatches": [] if passed else (mismatches or ["value differs"]),
        "plan": plan, "pipeline_data": [{"v": v[0]} for v in table] if table else None,
        "answer": answer, "answer_is_fallback": False, "answer_check": "pass",
        "cost_usd": 0.0003, "duration_s": 5.0, "llm_latency_s": 1.5,
        "llm_calls": [{"name": "planner", "error": e} for e in llm_errors],
    }
    r.update(extra)
    return r


def q(result, qid):
    return result["queries"][qid]


def test_reliable_query_is_fully_consistent():
    res = compute_stability([rec("Q01", i) for i in (1, 2, 3)])
    x = q(res, "Q01")
    assert (x["passes"], x["runs"], x["status"]) == (3, 3, "reliable")
    assert x["plan_consistent"] is True and x["table_consistent"] is True
    assert x["answer_numbers_consistent"] is True


def test_flaky_query():
    runs = [rec("Q06", 1), rec("Q06", 2, passed=False), rec("Q06", 3)]
    x = q(compute_stability(runs), "Q06")
    assert x["status"] == "flaky" and x["passes"] == 2


def test_broken_query_same_vs_different_failure():
    same = compute_stability([rec("Q41", i, passed=False, mismatches=["wrong total"]) for i in (1, 2, 3)])
    assert q(same, "Q41")["status"] == "broken" and q(same, "Q41")["same_failure"] is True
    diff = compute_stability([rec("Q41", 1, passed=False, mismatches=["wrong total"]),
                              rec("Q41", 2, passed=False, mismatches=["extra rows"])])
    assert q(diff, "Q41")["same_failure"] is False


def test_api_errors_are_kept_apart_from_real_failures():
    # Q03: one run lost to a timeout, the others pass -> flaky with 1 infra failure
    runs = [rec("Q03", 1), rec("Q03", 2, passed=False, llm_errors=["APITimeoutError: slow"]), rec("Q03", 3)]
    x = q(compute_stability(runs), "Q03")
    assert x["status"] == "flaky" and x["infra_failures"] == 1

    # Q04: every run lost to API errors -> infra_only, not "broken"
    all_infra = [rec("Q04", i, passed=False, llm_errors=["RateLimitError: Error code: 429"]) for i in (1, 2)]
    assert q(compute_stability(all_infra), "Q04")["status"] == "infra_only"

    # Validation errors from the LLM are NOT infra
    real = [rec("Q05", 1, passed=False, llm_errors=["Pydantic validation failed"])]
    assert q(compute_stability(real), "Q05")["status"] == "broken"


def test_plan_consistency_ignores_key_order_and_output_names_but_sees_real_changes():
    reordered = [{"step": 1, "tool": "aggregate_column", "input": "original_df", "output": "other_name",
                  "parameters": {"new_col_name": "Sales_sum", "operation": "sum", "col_name": "Sales"}}]
    same = compute_stability([rec("Q01", 1), rec("Q01", 2, plan=reordered)])
    assert q(same, "Q01")["plan_consistent"] is True

    changed = compute_stability([rec("Q01", 1), rec("Q01", 2, plan=PLAN_B)])
    assert q(changed, "Q01")["plan_consistent"] is False and q(changed, "Q01")["distinct_plans"] == 2


def test_answer_numbers_compare_numbers_not_wording():
    same_numbers = compute_stability([rec("Q01", 1, answer="Sales were $100.00."),
                                      rec("Q01", 2, answer="The total came to $100.00 overall.")])
    assert q(same_numbers, "Q01")["answer_numbers_consistent"] is True
    diff_numbers = compute_stability([rec("Q01", 1, answer="Sales were $100."),
                                      rec("Q01", 2, answer="Sales were $200.")])
    assert q(diff_numbers, "Q01")["answer_numbers_consistent"] is False


def test_fallback_answers_are_excluded_from_number_comparison():
    runs = [rec("Q01", 1, answer="Sales were $100."),
            rec("Q01", 2, answer="Sales_sum: 999", answer_is_fallback=True)]
    assert q(compute_stability(runs), "Q01")["answer_numbers_consistent"] is None  # only one comparable


def test_table_difference_detected():
    runs = [rec("Q11", 1, table=((1.0,), (2.0,))), rec("Q11", 2, table=((1.0,), (3.0,)))]
    assert q(compute_stability(runs), "Q11")["table_consistent"] is False


def test_multi_turn_records_use_outcome_and_have_no_table():
    runs = [{"id": "MT03", "repeat": i, "outcome": o, "plan": PLAN_A, "answer": "ok",
             "answer_check": "no_numbers", "cost_usd": 0.001, "duration_s": 9.0, "mismatches": []}
            for i, o in ((1, "pass"), (2, "fail"), (3, "skipped"))]
    x = q(compute_stability(runs), "MT03")
    assert x["multi_turn"] is True and x["passes"] == 1 and x["status"] == "flaky"
    assert x["table_consistent"] is None and x["plan_consistent"] is True


def test_accuracy_per_repeat_mean_and_spread():
    runs = []
    for qid in ("Q01", "Q02"):
        runs += [rec(qid, 1), rec(qid, 2, passed=(qid == "Q01")), rec(qid, 3, passed=(qid == "Q01"))]
    s = compute_stability(runs)["summary"]
    assert s["accuracy_per_repeat"] == {1: 1.0, 2: 0.5, 3: 0.5}
    assert s["accuracy_min"] == 0.5 and s["accuracy_max"] == 1.0
    assert s["accuracy_mean"] == pytest.approx(0.6667, abs=1e-4)
    assert s["status_counts"] == {"reliable": 1, "flaky": 1, "broken": 0, "infra_only": 0}


def test_single_repeat_works_and_reports_cannot_tell():
    res = compute_stability([rec("Q01", 1)])
    x = q(res, "Q01")
    assert x["status"] == "reliable" and x["plan_consistent"] is None
    assert res["summary"]["plan_identical_share"] is None


def test_report_text_and_cli_saves_files(tmp_path, capsys):
    runs = [rec("Q01", i) for i in (1, 2, 3)] + [rec("Q06", 1), rec("Q06", 2, passed=False), rec("Q06", 3)]
    src = tmp_path / "eval_x.json"
    src.write_text(json.dumps({"aggregate": {}, "records": runs}), encoding="utf-8")

    text = render_report(compute_stability(load_records([str(src)])))
    assert "Q01" in text and "reliable" in text and "flaky" in text and "Accuracy per repeat" in text

    out = tmp_path / "out"
    assert main([str(src), "--out-dir", str(out)]) == 0
    saved = sorted(p.suffix for p in out.iterdir())
    assert saved == [".json", ".txt"]
    capsys.readouterr()


# ---------------------------------------------------------------- refinements found in the first real B3c run
def no_gt(qid, repeat, status, **kw):
    """A compound case (Q38-Q47): no ground truth, the right behaviour is to refuse."""
    r = rec(qid, repeat, passed=False, plan=[] if status == "unsolvable" else PLAN_A, table=None,
            answer=None if status == "unsolvable" else "Total is $100.", **kw)
    r.update({"gt_data": None, "pipeline_status": status, "mismatches": ["Pipeline returned no result"]})
    return r


def test_no_ground_truth_case_passes_only_when_the_agent_refuses():
    runs = [no_gt("Q38", 1, "success"), no_gt("Q38", 2, "unsolvable"), no_gt("Q38", 3, "unsolvable")]
    x = q(compute_stability(runs), "Q38")
    assert (x["passes"], x["status"], x["expects_refusal"]) == (2, "flaky", True)

    always_answers = compute_stability([no_gt("Q41", i, "success") for i in (1, 2, 3)])
    x = q(always_answers, "Q41")
    assert x["status"] == "broken" and x["same_failure"] is True

    always_refuses = compute_stability([no_gt("Q43", i, "unsolvable") for i in (1, 2, 3)])
    assert q(always_refuses, "Q43")["status"] == "reliable"


def test_normal_case_is_not_treated_as_expecting_refusal():
    runs = [rec("Q01", i, gt_data=[{"v": 1}]) for i in (1, 2)]
    assert q(compute_stability(runs), "Q01")["expects_refusal"] is False


def test_list_numbering_and_rounding_do_not_count_as_different_numbers():
    listed = "The top five states are:\n\n1. California $457,687.63\n2. Texas $170,188.05"
    prose = "California leads with $457,687.63, followed by Texas at $170,188.05."
    assert q(compute_stability([rec("Q11", 1, answer=listed), rec("Q11", 2, answer=prose)]),
             "Q11")["answer_numbers_consistent"] is True

    rounded = [rec("Q41", 1, answer="Total profit is $286,397.02."),
               rec("Q41", 2, answer="Total profit is about $286,397.")]
    assert q(compute_stability(rounded), "Q41")["answer_numbers_consistent"] is True


def test_an_answer_that_adds_extra_numbers_is_still_consistent_but_different_numbers_are_not():
    base = "The average discount is 0.174."
    extra = "The average discount is 0.174, which means a 17.4% discount."
    assert q(compute_stability([rec("Q15", 1, answer=base), rec("Q15", 2, answer=extra)]),
             "Q15")["answer_numbers_consistent"] is True

    changed = [rec("Q15", 1, answer="The average discount is 0.174."),
               rec("Q15", 2, answer="The average discount is 0.250.")]
    assert q(compute_stability(changed), "Q15")["answer_numbers_consistent"] is False


# ---------------------------------------------------------------- invented column names (seen in the real Q17 / Q27 runs)
def q17_plan(col):
    return [
        {"step": 1, "tool": "extract_date_part", "input": "original_df", "output": "a",
         "parameters": {"col_name": "Order Date", "part": "month", "new_col_name": col}},
        {"step": 2, "tool": "groupby_aggregate", "input": "a", "output": "b",
         "parameters": {"group_col": col, "agg_col": {"Order Date": "count"}}},
        {"step": 3, "tool": "sort", "input": "b", "output": "c",
         "parameters": {"sort_col": {"Order Date_count": "desc"}}},
    ]


def q27_plan(col):
    return [
        {"step": 1, "tool": "column_arithmetic", "input": "original_df", "output": "a",
         "parameters": {"col1": "Ship Date", "col2": "Order Date", "operation": "-", "new_col_name": col}},
        {"step": 2, "tool": "groupby_aggregate", "input": "a", "output": "b",
         "parameters": {"group_col": "Category", "agg_col": {col: "mean"}}},
        {"step": 3, "tool": "sort", "input": "b", "output": "c",
         "parameters": {"sort_col": {col + "_mean": "desc"}}},
    ]


def test_invented_column_names_do_not_make_plans_differ():
    runs = [rec("Q17", 1, plan=q17_plan("Order Month")), rec("Q17", 2, plan=q17_plan("OrderMonth"))]
    assert q(compute_stability(runs), "Q17")["plan_consistent"] is True

    runs = [rec("Q27", 1, plan=q27_plan("shipping_time")), rec("Q27", 2, plan=q27_plan("shipping_days"))]
    assert q(compute_stability(runs), "Q27")["plan_consistent"] is True  # derived `<name>_mean` handled too


def test_a_real_logic_change_still_shows_as_a_different_plan():
    changed = q27_plan("shipping_days")
    changed[1]["parameters"]["agg_col"] = {"shipping_days": "max"}  # mean -> max
    runs = [rec("Q27", 1, plan=q27_plan("shipping_time")), rec("Q27", 2, plan=changed)]
    assert q(compute_stability(runs), "Q27")["plan_consistent"] is False


def test_tables_with_renamed_or_reordered_columns_are_the_same_table():
    a = rec("Q46", 1, pipeline_data=[{"Region": "West", "Profit_sum": 108418.45, "Order Date_count": 3140}])
    b = rec("Q46", 2, pipeline_data=[{"Region": "West", "Order Date_count": 3140, "Profit_sum": 108418.45}])
    c = rec("Q27", 1, pipeline_data=[{"Category": "X", "shipping_time_mean": 3.96}])
    d = rec("Q27", 2, pipeline_data=[{"Category": "X", "shipping_days_mean": 3.96}])
    assert q(compute_stability([a, b]), "Q46")["table_consistent"] is True
    assert q(compute_stability([c, d]), "Q27")["table_consistent"] is True
    different = rec("Q27", 2, pipeline_data=[{"Category": "X", "shipping_days_mean": 4.50}])
    assert q(compute_stability([c, different]), "Q27")["table_consistent"] is False
