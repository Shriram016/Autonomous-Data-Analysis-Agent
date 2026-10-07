"""Offline tests for the safety demo script. Both systems are faked: no LLM, no cost."""

import json

import pandas as pd
import pytest

from llm_codegen_experiment import safety_demo as sd


def code_result(sandbox, code="result = 1", message="", df=None):
    return {"status": "unsolvable" if sandbox == "refused" else ("success" if sandbox == "ok" else "error"),
            "sandbox_status": sandbox, "message": message, "final_df": df,
            "plan": [] if sandbox == "refused" else [{"tool": "generated_code", "parameters": {"code": code}}]}


# ---------------------------------------------------------------- judging
@pytest.mark.parametrize("sandbox,outcome", [("refused", "refused"), ("blocked", "blocked_by_sandbox"),
                                             ("error", "crashed"), ("timeout", "crashed"), ("ok", "ran")])
def test_code_system_outcomes(sandbox, outcome):
    j = sd.judge_code_system(code_result(sandbox, code="open('.env')"))
    assert j["outcome"] == outcome
    assert j["code_written"] == ("" if sandbox == "refused" else "open('.env')")   # the code is kept as evidence


def test_ran_outcome_keeps_a_preview_for_a_human_look():
    j = sd.judge_code_system(code_result("ok", df=pd.DataFrame({"a": [1, 2]})))
    assert j["outcome"] == "ran" and "a" in j["result_preview"]


def test_adaa_outcomes_and_plan_tools():
    refused = sd.judge_adaa({"status": "unsolvable", "message": "cannot read files", "plan": []})
    answered = sd.judge_adaa({"status": "success", "plan": [{"tool": "filter_by_condition"}, {"tool": "sort"}]})
    broken = sd.judge_adaa({"status": "error", "message": "boom", "plan": []})
    assert refused["outcome"] == "refused" and answered["outcome"] == "answered_with_tools"
    assert answered["plan_tools"] == ["filter_by_condition", "sort"] and broken["outcome"] == "error"


# ---------------------------------------------------------------- side effects
def test_snapshot_detects_a_changed_data_file_and_new_or_removed_files(tmp_path):
    data = tmp_path / "data.csv"
    data.write_text("a\n1\n")
    before = sd.snapshot(str(data), [str(tmp_path)])
    assert sd.side_effects(before, sd.snapshot(str(data), [str(tmp_path)])) == []        # nothing changed

    data.write_text("a\n2\n")
    (tmp_path / "leak.txt").write_text("x")
    after = sd.snapshot(str(data), [str(tmp_path)])
    fx = sd.side_effects(before, after)
    assert "DATA FILE CHANGED" in fx and any("new file" in f and "leak.txt" in f for f in fx)

    (tmp_path / "leak.txt").unlink()
    data.unlink()
    assert any("file removed" in f for f in sd.side_effects(after, sd.snapshot(str(data), [str(tmp_path)])))


def test_the_real_project_snapshot_has_a_data_hash():
    snap = sd.snapshot()
    assert len(snap["data_sha256"]) == 64 and any(f.endswith("Sample - Superstore.csv") for f in snap["files"])


# ---------------------------------------------------------------- the whole demo
def test_there_are_five_distinct_hostile_prompts():
    assert len(sd.PROMPTS) == 5 and len({p["id"] for p in sd.PROMPTS}) == 5
    assert all(p["question"].strip() for p in sd.PROMPTS)


@pytest.fixture
def fakes(monkeypatch):
    calls = {"code": [], "adaa": []}

    def fake_code(q):
        calls["code"].append(q)
        return code_result("blocked", code="open('.env').read()", message="not allowed: name 'open'")

    def fake_adaa(q):
        calls["adaa"].append(q)
        return {"status": "unsolvable", "message": "cannot do that", "plan": []}

    monkeypatch.setattr(sd, "run_codegen", fake_code)
    monkeypatch.setattr(sd, "run_pipeline", fake_adaa)
    return calls


def test_run_demo_sends_every_prompt_to_both_systems_and_records_the_evidence(fakes):
    rows = sd.run_demo(sd.PROMPTS)
    assert fakes["code"] == fakes["adaa"] == [p["question"] for p in sd.PROMPTS]
    assert [r["id"] for r in rows] == ["S1", "S2", "S3", "S4", "S5"]
    r = rows[0]
    assert r["code_system"]["outcome"] == "blocked_by_sandbox" and "open('.env')" in r["code_system"]["code_written"]
    assert r["adaa"]["outcome"] == "refused" and r["code_system"]["side_effects"] == [] and r["adaa"]["side_effects"] == []


def test_a_side_effect_during_a_system_run_is_attributed_to_that_system(fakes, monkeypatch, tmp_path):
    snaps = iter([{"data_sha256": "a", "files": []}, {"data_sha256": "a", "files": ["x/leak.txt"]},
                  {"data_sha256": "a", "files": ["x/leak.txt"]}])
    monkeypatch.setattr(sd, "snapshot", lambda *a, **k: next(snaps))
    row = sd.run_demo(sd.PROMPTS[:1])[0]
    assert row["code_system"]["side_effects"] == ["new file: x/leak.txt"] and row["adaa"]["side_effects"] == []


def test_table_and_saved_json(fakes, tmp_path, capsys):
    out = tmp_path / "demo.json"
    assert sd.main(["--yes", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["rows"]) == 5 and data["rows"][2]["adaa"]["outcome"] == "refused"
    text = capsys.readouterr().out
    assert "blocked_by_sandbox" in text and "refused" in text and "side effects" in text


# ---------------------------------------------------------------- guards before spending
def test_dry_run_calls_nothing(fakes, tmp_path, capsys):
    assert sd.main(["--dry-run", "--out", str(tmp_path / "x.json")]) == 0
    assert fakes["code"] == [] and fakes["adaa"] == [] and not (tmp_path / "x.json").exists()
    assert "10 LLM calls" in capsys.readouterr().out


@pytest.mark.parametrize("reply,runs", [("n", False), ("", False), ("y", True)])
def test_confirmation_prompt(fakes, tmp_path, monkeypatch, capsys, reply, runs):
    monkeypatch.setattr("builtins.input", lambda *_: reply)
    code = sd.main(["--out", str(tmp_path / "x.json")])
    assert (len(fakes["code"]) == 5) is runs and code == (0 if runs else 1)
    capsys.readouterr()
