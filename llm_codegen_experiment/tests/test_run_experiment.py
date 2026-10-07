"""Offline tests for the experiment runner (run_experiment.py). The code-writing system is faked."""

import json

import pytest

import eval.run_eval as single_mod
import eval.run_full_eval as harness
import eval.run_multiturn_eval as multi_mod
from llm_codegen_experiment import run_experiment as rx

PLANNER = {"name": "codegen", "model": "openai/gpt-oss-20b", "input_tokens": 700, "output_tokens": 60,
           "total_tokens": 760, "latency_s": 0.4, "error": None}


@pytest.fixture
def fake_codegen(monkeypatch):
    df = single_mod._load_dataset()
    gt = {c.query: c.ground_truth_fn(df) for c in harness.TEST_CASES if c.ground_truth_fn}
    calls = []

    def fake(query, session_id=None):
        calls.append(query)
        table = gt.get(query)
        if table is None:
            return {"status": "error", "message": "error: no table", "final_df": None, "answer": None,
                    "plan": [], "trace": [], "events": [], "total_executions": 1, "llm_calls": [dict(PLANNER)]}
        return {"status": "success", "message": "", "final_df": table, "answer": None,
                "plan": [{"step": 1, "tool": "generated_code", "parameters": {"code": "result = 1"},
                          "input": "df", "output": "result"}],
                "trace": [], "events": [], "total_executions": 1, "llm_calls": [dict(PLANNER)]}

    monkeypatch.setattr(rx, "run_codegen", fake)
    monkeypatch.setattr(harness, "_ping_llm", lambda: (True, "models reachable (fake)"))
    return calls


def test_runner_drives_the_harness_with_the_codegen_system(fake_codegen, tmp_path, capsys):
    out = tmp_path / "res"
    assert rx.main(["--yes", "--out-dir", str(out), "--only", "single", "--ids", "Q01,Q06"]) == 0
    assert fake_codegen == ["What is the total sales across all orders?",
                            "What are the total sales for the Technology category?"]
    run = next(out.iterdir())
    recs = json.loads((run / "results.json").read_text(encoding="utf-8"))["records"]
    assert [r["id"] for r in recs] == ["Q01", "Q06"] and all(r["passed"] for r in recs)
    assert recs[0]["plan"][0]["tool"] == "generated_code"      # the generated code is kept in the record
    assert recs[0]["answer_is_fallback"] is False               # no answer step is not a fallback
    capsys.readouterr()


def test_manifest_says_which_system_and_which_code(fake_codegen, tmp_path, capsys):
    out = tmp_path / "res"
    rx.main(["--yes", "--out-dir", str(out), "--only", "single", "--ids", "Q01"])
    m = json.loads((next(out.iterdir()) / "manifest.json").read_text(encoding="utf-8"))
    assert m["system"] == "codegen"
    assert m["codegen"]["history_window"] == 3 and len(m["codegen"]["code_sha256_16"]) == 16
    assert len(m["codegen"]["system_prompt_sha256_16"]) == 16
    capsys.readouterr()


def test_the_original_pipelines_are_restored_afterwards(fake_codegen, tmp_path, capsys):
    before = (single_mod.run_pipeline, multi_mod.run_pipeline)
    rx.main(["--yes", "--out-dir", str(tmp_path / "res"), "--only", "single", "--ids", "Q01"])
    assert (single_mod.run_pipeline, multi_mod.run_pipeline) == before
    capsys.readouterr()


def test_the_pipelines_are_restored_even_if_the_run_crashes(fake_codegen, tmp_path, monkeypatch, capsys):
    before = (single_mod.run_pipeline, multi_mod.run_pipeline)
    monkeypatch.setattr(rx, "run_codegen", lambda q, session_id=None: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        rx.main(["--yes", "--out-dir", str(tmp_path / "res"), "--only", "single", "--ids", "Q01"])
    assert (single_mod.run_pipeline, multi_mod.run_pipeline) == before
    capsys.readouterr()


def test_default_results_folder_is_inside_the_experiment_folder(fake_codegen, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rx, "RESULTS_DIR", str(tmp_path / "default_res"))
    rx.main(["--dry-run"])
    assert (tmp_path / "default_res").exists()
    assert rx.RESULTS_DIR.endswith("default_res") and "llm_codegen_experiment" in rx.__file__
    capsys.readouterr()


def test_summary_is_labelled_as_the_codegen_system(fake_codegen, tmp_path, capsys):
    out = tmp_path / "res"
    rx.main(["--yes", "--out-dir", str(out), "--only", "single", "--ids", "Q01"])
    run = next(out.iterdir())
    text = (run / "summary.txt").read_text(encoding="utf-8")
    assert "CODEGEN FULL EVAL SUMMARY" in text and "writes the code" in text and "ADAA FULL" not in text
    assert json.loads((run / "manifest.json").read_text(encoding="utf-8"))["system"] == "codegen"
    assert json.loads((run / "results.json").read_text(encoding="utf-8"))["manifest"]["system"] == "codegen"
    capsys.readouterr()


def test_a_refusal_scores_like_adaas_refusals_in_the_harness(monkeypatch, tmp_path, capsys):
    """Q38 has no ground truth (correct = refuse): a REFUSE reply passes; answering it fails; refusing an answerable question fails."""
    refuse = {"status": "unsolvable", "message": "needs two results", "final_df": None, "answer": None,
              "plan": [], "trace": [], "events": [], "total_executions": 0, "llm_calls": [dict(PLANNER)]}
    monkeypatch.setattr(rx, "run_codegen", lambda q, session_id=None: refuse)
    monkeypatch.setattr(harness, "_ping_llm", lambda: (True, "fake"))
    out = tmp_path / "res"
    rx.main(["--yes", "--out-dir", str(out), "--only", "single", "--ids", "Q38,Q01"])
    recs = {r["id"]: r for r in json.loads((next(out.iterdir()) / "results.json").read_text(encoding="utf-8"))["records"]}
    assert recs["Q38"]["passed"] is True and recs["Q38"]["expected_behavior"] == "refuse"
    assert recs["Q01"]["passed"] is False and harness.failure_kind(recs["Q01"]) == "refused_but_answerable"
    capsys.readouterr()
