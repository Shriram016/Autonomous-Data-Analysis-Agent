"""Offline tests for Part C: the failure labeller (eval/failure_labels.py), on made-up records."""

import json

import pytest

import eval.failure_labels as fl


def rec(qid, kind="single", passed=False, status="success", plan=("aggregate_column",), tags=(),
        gt=None, got=None, expected="answer", **extra):
    r = {
        "id": qid, "kind": kind, "repeat": 1, "passed": passed, "expected_behavior": expected,
        "pipeline_status": status, "plan": [{"tool": t} for t in plan], "tags": list(tags),
        "gt_data": gt, "pipeline_data": got, "mismatches": ["Value[0]: GT=1, Pipeline=2"],
        "pipeline_message": "", "llm_calls": [], "trace": [], "events": [], "answer_check": "pass",
    }
    r.update(extra)
    return r


def outcome(r, meta=None):
    return fl.label_outcome(r, meta or {})


def test_passing_case_has_no_outcome_label():
    assert outcome(rec("Q01", passed=True)) is None


def test_missing_filter_single_turn():
    lbl = outcome(rec("Q06", tags=["filter", "aggregation"]))
    assert lbl["category"] == "planner_missing_filter" and lbl["confidence"] == "high"


def test_filter_present_but_wrong_value_is_not_missing_filter():
    lbl = outcome(rec("Q99", tags=["filter"], plan=("filter_by_condition", "aggregate_column")))
    assert lbl["category"] == "planner_other_wrong_result" and lbl["confidence"] == "review"


def test_missing_filter_carried_from_an_earlier_turn():
    r = rec("MT03", kind="multi", num_turns=2,
            turns=[{"plan_tools": ["filter_by_condition", "aggregate_column"], "status": "success"},
                   {"plan_tools": ["aggregate_column"], "status": "success"}])
    assert outcome(r)["category"] == "planner_missing_filter"


def test_extra_rows_make_a_superset_even_if_no_filter_ran():
    gt = [{"year": 2014, "s": 1.0}, {"year": 2015, "s": 2.0}]
    got = gt + [{"year": 2017, "s": 9.0}]
    r = rec("MT16", kind="multi", num_turns=4, plan=("extract_date_part", "groupby_aggregate"), gt=gt, got=got,
            turns=[{"plan_tools": ["filter_by_condition"], "status": "success"}, {"plan_tools": [], "status": "success"}])
    assert outcome(r)["category"] == "planner_superset_result"


def test_wrong_step_order_when_a_context_turn_errors():
    r = rec("MT07", kind="multi", outcome="skipped", plan=(), pipeline_status=None,
            turns=[{"plan_tools": ["aggregate_column", "filter_by_condition"], "status": "error",
                    "message": "Column 'Segment' not found in DataFrame."}])
    lbl = outcome(r)
    assert lbl["category"] == "planner_wrong_step_order" and lbl["confidence"] == "high"


def test_refusal_cases():
    refused = outcome(rec("Q33", status="unsolvable", plan=(), pipeline_message="cannot answer"))
    assert refused["category"] == "planner_refused_answerable"

    answered = outcome(rec("Q41", expected="refuse", status="success", gt=None, got=[{"v": 1}]))
    assert answered["category"] == "planner_answered_should_refuse"
    assert any("faithful" in e for e in answered["evidence"])


def test_api_error_is_infrastructure():
    r = rec("Q03", status="error", llm_calls=[{"error": "APITimeoutError: slow"}])
    assert outcome(r)["category"] == "infrastructure"


def test_four_turn_wrong_result_is_context_loss_for_review():
    r = rec("MT13", kind="multi", num_turns=4, plan=("filter_by_condition", "aggregate_column"),
            turns=[{"plan_tools": ["x"], "status": "success"}] * 4)
    lbl = outcome(r)
    assert lbl["category"] == "context_loss" and lbl["confidence"] == "review"


def test_answer_label_applies_even_when_the_case_passed():
    r = rec("Q37", passed=True, answer_check="fail", answer_numbers_unsupported=["$455,255.98"])
    lbl = fl.label_answer(r)
    assert lbl["category"] == "answer_wrong_number" and "correct" in lbl["evidence"][1]
    assert fl.label_answer(rec("Q01", answer_check="pass")) is None


def test_label_run_gives_one_entry_per_labelled_case_with_both_labels():
    both = rec("Q41", expected="refuse", answer_check="fail", answer_numbers_unsupported=["$1"])
    clean = rec("Q01", passed=True)
    entries = fl.label_run([both, clean])
    assert [e["id"] for e in entries] == ["Q41"]
    assert [l["dimension"] for l in entries[0]["labels"]] == ["outcome", "answer"]


def test_guardrail_caught_means_it_fired_and_the_case_ended_correct():
    fired = {"trace": [{"critic": "fail", "critic_check": "not_none"}], "events": [{"type": "param_fix"}]}
    saved = fl.label_run([rec("Q23", passed=True, answer_check="fail", answer_numbers_unsupported=["1"], **fired)])
    still_wrong = fl.label_run([rec("Q42", passed=False, **fired)])
    untouched = fl.label_run([rec("Q06", passed=False, tags=["filter"])])
    assert saved[0]["caught_by_guardrail"] is True
    assert still_wrong[0]["caught_by_guardrail"] is False and still_wrong[0]["guardrail"]["any_fired"] is True
    assert untouched[0]["guardrail"]["any_fired"] is False


def test_human_override_wins_and_is_marked_reviewed():
    r = rec("MT13", kind="multi", num_turns=4, turns=[{"plan_tools": [], "status": "success"}] * 4)
    entries = fl.label_run([r], {"MT13": {"category": "planner_other_wrong_result", "note": "wrong filters, not memory"}})
    lbl = entries[0]["labels"][0]
    assert lbl["category"] == "planner_other_wrong_result" and lbl["confidence"] == "reviewed"
    assert lbl["source"] == "user_review" and "wrong filters" in lbl["evidence"][-1]


def test_breakdown_table_counts_cases_components_and_caught():
    recs = [rec("Q06", tags=["filter"]), rec("Q07", tags=["filter"]),
            rec("Q33", status="unsolvable", plan=()),
            rec("MT13", kind="multi", num_turns=4, turns=[{"plan_tools": [], "status": "success"}] * 4)]
    entries = fl.label_run(recs)
    table = {r["category"]: r for r in fl.build_table(entries)}
    mf = table["Planner: missing filter"]
    assert mf["count"] == 2 and mf["cases"] == ["Q06", "Q07"] and mf["component"] == "Planner (LLM)"
    assert table["Context: earlier turn not carried forward"]["review"] == ["MT13"]
    text = fl.render_breakdown(entries, [], total=10, failed=4)
    assert "Failures caught: 0/4" in text and "NEEDS YOUR REVIEW" in text


def test_write_outputs_creates_the_three_files(tmp_path, monkeypatch):
    run = tmp_path / "full_x"
    run.mkdir()
    records = [{"kind": "single", **rec("Q06", tags=["filter"])}, {"kind": "single", **rec("Q01", passed=True)}]
    (run / "records.jsonl").write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    text = fl.write_outputs(str(run), overrides={})
    assert sorted(p.name for p in run.iterdir()) == [
        "failure_breakdown.csv", "failure_breakdown.txt", "failure_labels.json", "records.jsonl"]
    assert "Planner: missing filter" in text
    data = json.loads((run / "failure_labels.json").read_text(encoding="utf-8"))
    assert data["entries"][0]["id"] == "Q06"


def test_earlier_filter_dropped_in_a_four_turn_case_is_context_loss_for_review_not_missing_filter():
    r = rec("MT15", kind="multi", num_turns=4, plan=("extract_date_part", "groupby_aggregate"),
            gt=[{"y": 2015, "s": 1.0}], got=[{"y": 2015, "n": 5}],
            turns=[{"plan_tools": ["filter_by_condition"], "status": "success"}] * 3
                  + [{"plan_tools": ["groupby_aggregate"], "status": "success"}])
    lbl = outcome(r)
    assert lbl["category"] == "context_loss" and lbl["confidence"] == "review"


def test_override_can_relabel_a_review_case_as_planner_context_misuse():
    r = rec("MT15", kind="multi", num_turns=4, turns=[{"plan_tools": [], "status": "success"}] * 4)
    entries = fl.label_run([r], {"MT15": {"category": "planner_context_misuse", "note": "turns were in memory"}})
    lbl = entries[0]["labels"][0]
    assert lbl["category"] == "planner_context_misuse" and lbl["component"] == "Planner (LLM)"
    assert lbl["confidence"] == "reviewed" and lbl["label"].startswith("Planner failure: ignored")


def test_the_committed_overrides_file_is_valid():
    ov = fl.load_overrides()
    assert set(ov) >= {"MT13", "MT15"}
    assert all(v["category"] in fl.CATEGORIES and v.get("note") for v in ov.values())
