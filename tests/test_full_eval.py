"""Offline tests for the full-eval runner (eval/run_full_eval.py).

Both pipelines are faked (they return the ground truth, or "unsolvable" for the cases that must
be refused), so the whole 47 + 16 case run takes a second and costs nothing.
"""

import json
import os

import pandas as pd
import pytest

import eval.run_eval as single_mod
import eval.run_full_eval as rfe
import eval.run_multiturn_eval as multi_mod

PLANNER = {"name": "planner", "model": "openai/gpt-oss-20b", "input_tokens": 2000, "output_tokens": 100,
           "total_tokens": 2100, "latency_s": 0.5, "error": None}
ANSWER = {"name": "answer_gen", "model": "openai/gpt-oss-20b", "input_tokens": 300, "output_tokens": 80,
          "total_tokens": 380, "latency_s": 0.3, "error": None}


@pytest.fixture(scope="module")
def world():
    df = single_mod._load_dataset()
    cases = rfe.TEST_CASES + rfe.TEST_CASES_2 + rfe.TEST_CASES_3
    by_query = {c.query: c for c in cases}
    return {
        "single": by_query,
        "gt": {q: c.ground_truth_fn(df) for q, c in by_query.items() if c.ground_truth_fn},
        "multi_gt": {c.turns[-1].query: c.turns[-1].ground_truth_fn(df) for c in rfe.MULTITURN_TEST_CASES},
    }


class Fake:
    """Fake pipelines for both runners, with call counting and optional failure injection."""

    def __init__(self, world):
        self.w = world
        self.calls = 0
        self.crash_on_call = None      # raise KeyboardInterrupt on this call number
        self.api_error_for = None      # single-turn query that should fail with an API timeout

    def single(self, query):
        self.calls += 1
        if self.crash_on_call == self.calls:
            raise KeyboardInterrupt("simulated Ctrl+C")
        if query == self.api_error_for:
            return {"status": "error", "message": "Groq API timed out after 90s.", "final_df": None,
                    "plan": [], "trace": [], "events": [], "total_executions": 0, "answer": None,
                    "llm_calls": [dict(PLANNER, input_tokens=None, output_tokens=None, total_tokens=None,
                                       error="APITimeoutError: slow")]}
        if query in self.w["gt"]:
            return {"status": "success", "final_df": self.w["gt"][query], "plan": [], "trace": [], "events": [],
                    "total_executions": 1, "answer": "ok", "llm_calls": [dict(PLANNER), dict(ANSWER)]}
        return {"status": "unsolvable", "message": "cannot be answered", "final_df": None, "plan": [],
                "trace": [], "events": [], "total_executions": 0, "answer": None, "llm_calls": [dict(PLANNER)]}

    def multi(self, query, session_id=None):
        self.calls += 1
        gt = self.w["multi_gt"].get(query, pd.DataFrame({"v": [1]}))
        return {"status": "success", "final_df": gt, "plan": [], "trace": [], "events": [],
                "total_executions": 1, "answer": "ok", "llm_calls": [dict(PLANNER), dict(ANSWER)]}


@pytest.fixture
def fake(world, monkeypatch):
    f = Fake(world)
    monkeypatch.setattr(single_mod, "run_pipeline", f.single)
    monkeypatch.setattr(multi_mod, "run_pipeline", f.multi)
    monkeypatch.setattr(rfe, "_ping_llm", lambda: (True, "models reachable (fake)"))
    return f


def run_dir_of(out):
    return next(p for p in out.iterdir() if p.name.startswith("full_"))


def jsonl_count(d):
    return len(rfe.load_jsonl(str(d / "records.jsonl")))


# ---------------------------------------------------------------- normal run
def test_full_run_writes_every_artifact_and_scores_correctly(fake, tmp_path, capsys):
    assert rfe.main(["--yes", "--out-dir", str(tmp_path)]) == 0
    d = run_dir_of(tmp_path)
    assert sorted(p.name for p in d.iterdir()) == [
        "console.log", "manifest.json", "records.jsonl", "results.csv", "results.json", "summary.txt"]

    res = json.loads((d / "results.json").read_text(encoding="utf-8"))
    recs = res["records"]
    assert len(recs) == 63 and jsonl_count(d) == 63
    assert sum(r["kind"] == "single" for r in recs) == 47 and sum(r["kind"] == "multi" for r in recs) == 16
    assert all(r["passed"] for r in recs)                       # fakes do the right thing everywhere
    refuse = [r for r in recs if r["expected_behavior"] == "refuse"]
    assert len(refuse) == 10 and all(r["pipeline_status"] == "unsolvable" for r in refuse)

    m = res["manifest"]
    assert m["status"] == "complete" and m["totals"]["records"] == 63 and m["totals"]["passed"] == 63
    assert len(m["dataset"]["sha256"]) == 64 and m["settings"]["ANSWER_MODEL"]
    assert m["git"]["commit"] and "src/core/planner.py" in m["code_hashes"]
    assert m["prices"]["as_of"] and m["plan"] == {"single_cases": 47, "multi_cases": 16, "runs_expected": 63}

    summary = (d / "summary.txt").read_text(encoding="utf-8")
    assert "All cases" in summary and "63/63" in summary and "FAILURES BY KIND (0)" in summary
    assert "ADAA Evaluation Pipeline" in (d / "console.log").read_text(encoding="utf-8")  # console mirrored
    capsys.readouterr()


def test_multiturn_records_carry_the_evidence_part_c_needs(fake, tmp_path, capsys):
    rfe.main(["--yes", "--out-dir", str(tmp_path), "--only", "multi", "--ids", "MT03"])
    d = run_dir_of(tmp_path)
    (r,) = rfe.load_jsonl(str(d / "records.jsonl"))
    assert r["kind"] == "multi" and r["expected_behavior"] == "answer" and r["passed"] is True
    assert r["gt_data"] and r["pipeline_data"]                   # final table and ground truth saved
    assert [t["query"] for t in r["turns"]][-1] == r["final_query"] and len(r["turns"]) == 2
    assert {"trace", "events", "plan", "llm_calls", "session_id"} <= set(r)
    capsys.readouterr()


# ---------------------------------------------------------------- crash safety and resume
def test_crash_loses_at_most_the_case_in_progress_and_resume_finishes_the_rest(fake, tmp_path, capsys):
    fake.crash_on_call = 10
    with pytest.raises(KeyboardInterrupt):
        rfe.main(["--yes", "--out-dir", str(tmp_path)])
    d = run_dir_of(tmp_path)
    assert jsonl_count(d) == 9                                   # nine finished cases were already on disk
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    assert m["status"] == "interrupted" and "KeyboardInterrupt" in m["error"]
    assert not (d / "results.json").exists()

    fake.crash_on_call, fake.calls = None, 0
    assert rfe.main(["--yes", "--resume", str(d)]) == 0
    assert fake.calls > 0
    # 54 single/multi pipeline runs were still needed (multi-turn cases make several calls each)
    recs = json.loads((d / "results.json").read_text(encoding="utf-8"))["records"]
    assert len(recs) == 63 and len({(r["kind"], r["id"]) for r in recs}) == 63   # exactly one per case
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    assert m["status"] == "complete" and m["events"][0]["already_done"] == 9
    capsys.readouterr()


def test_cases_lost_to_api_errors_are_rerun_on_resume_and_nothing_else(fake, world, tmp_path, capsys):
    victim = rfe.TEST_CASES[0]
    fake.api_error_for = victim.query
    rfe.main(["--yes", "--out-dir", str(tmp_path), "--only", "single"])
    d = run_dir_of(tmp_path)
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    assert m["status"] == "incomplete" and m["totals"]["lost_to_api_errors"] == 1
    assert [rfe.failure_kind(r) for r in rfe.load_jsonl(str(d / "records.jsonl")) if not r["passed"]] == ["api_error"]

    fake.api_error_for, fake.calls = None, 0
    rfe.main(["--yes", "--resume", str(d), "--only", "single"])
    assert fake.calls == 1                                       # only the lost case was run again
    assert jsonl_count(d) == 48                                  # 47 + the re-run (history kept)
    res = json.loads((d / "results.json").read_text(encoding="utf-8"))
    assert len(res["records"]) == 47 and all(r["passed"] for r in res["records"])
    assert res["manifest"]["status"] == "complete"
    capsys.readouterr()


def test_a_half_written_last_line_is_ignored(tmp_path):
    p = tmp_path / "records.jsonl"
    p.write_text(json.dumps({"kind": "single", "id": "Q01", "repeat": 1, "passed": True}) + "\n" + '{"kind": "sin',
                 encoding="utf-8")
    assert [r["id"] for r in rfe.load_jsonl(str(p))] == ["Q01"]


# ---------------------------------------------------------------- guards before spending anything
def test_dry_run_checks_everything_but_calls_no_pipeline(fake, tmp_path, capsys):
    assert rfe.main(["--dry-run", "--out-dir", str(tmp_path)]) == 0
    assert fake.calls == 0
    d = run_dir_of(tmp_path)
    assert json.loads((d / "manifest.json").read_text(encoding="utf-8"))["status"] == "dry_run"
    assert not (d / "records.jsonl").exists()
    out = capsys.readouterr().out
    assert "47 single-turn + 16 multi-turn" in out and "estimated cost" in out


def test_failed_preflight_runs_nothing_and_writes_nothing(fake, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rfe, "_ping_llm", lambda: (False, "NotFoundError: model not found"))
    assert rfe.main(["--yes", "--out-dir", str(tmp_path)]) == 2
    assert fake.calls == 0 and not any(p.name.startswith("full_") for p in tmp_path.iterdir())
    assert "Preflight failed" in capsys.readouterr().out


@pytest.mark.parametrize("reply,runs", [("n", False), ("", False), ("y", True)])
def test_confirmation_prompt(fake, tmp_path, monkeypatch, capsys, reply, runs):
    monkeypatch.setattr("builtins.input", lambda *_: reply)
    code = rfe.main(["--out-dir", str(tmp_path), "--only", "single", "--ids", "Q01"])
    assert (fake.calls == 1) is runs and code == (0 if runs else 1)
    capsys.readouterr()


# ---------------------------------------------------------------- scoring and kinds
def test_failure_kinds():
    base = {"passed": False, "llm_calls": [], "mismatches": [], "pipeline_message": ""}
    k = rfe.failure_kind
    assert k({**base, "passed": True}) == ""
    assert k({**base, "expected_behavior": "refuse", "pipeline_status": "success"}) == "answered_instead_of_refusing"
    assert k({**base, "expected_behavior": "answer", "pipeline_status": "unsolvable"}) == "refused_but_answerable"
    assert k({**base, "expected_behavior": "answer", "pipeline_status": "success"}) == "wrong_result"
    assert k({**base, "expected_behavior": "answer", "pipeline_status": "error",
              "llm_calls": [{"error": "APITimeoutError: x"}]}) == "api_error"
    assert k({**base, "outcome": "skipped", "expected_behavior": "answer"}) == "skipped_context_turn"


def test_repeats_are_kept_separate(fake, tmp_path, capsys):
    rfe.main(["--yes", "--out-dir", str(tmp_path), "--only", "single", "--ids", "Q01,Q05", "--repeats", "2"])
    d = run_dir_of(tmp_path)
    recs = json.loads((d / "results.json").read_text(encoding="utf-8"))["records"]
    assert sorted((r["id"], r["repeat"]) for r in recs) == [("Q01", 1), ("Q01", 2), ("Q05", 1), ("Q05", 2)]
    assert "Stability Report" in (d / "summary.txt").read_text(encoding="utf-8")
    capsys.readouterr()


def test_git_info_lists_uncommitted_files_with_intact_paths(monkeypatch):
    # `git status --porcelain` output starts with a space for unstaged changes; the first path must keep its first character
    monkeypatch.setattr(rfe, "_git", lambda *a: " M .claude/settings.local.json\n M eval/metrics.py"
                        if a[0] == "status" else "abc123")
    assert rfe._git_info()["uncommitted_tracked_files"] == [".claude/settings.local.json", "eval/metrics.py"]


# ---------------------------------------------------------------- --rebuild (free recompute from saved evidence)
def test_rebuild_recomputes_derived_fields_without_any_llm_call(fake, tmp_path, capsys):
    rfe.main(["--yes", "--out-dir", str(tmp_path), "--only", "single", "--ids", "Q41,Q01"])
    d = run_dir_of(tmp_path)
    path = d / "records.jsonl"
    recs = rfe.load_jsonl(str(path))
    refused = next(r for r in recs if r["id"] == "Q41")                 # no ground truth -> refused by the fake
    answered = next(r for r in recs if r["id"] == "Q01")
    # Simulate the old buggy flags: a refusal marked as a fallback, and a list-numbered answer marked as failing
    refused["answer_is_fallback"] = True
    answered["answer"] = "Total sales:\n1. All orders $2,297,200.86"
    answered["answer_check"] = "fail"
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")

    fake.calls = 0
    assert rfe.main(["--rebuild", str(d)]) == 0
    assert fake.calls == 0                                            # nothing was run
    out = {r["id"]: r for r in json.loads((d / "results.json").read_text(encoding="utf-8"))["records"]}
    assert out["Q41"]["answer_is_fallback"] is False                  # never reached the answer step
    assert out["Q01"]["answer_check"] in ("pass", "no_numbers", "n/a") # list numbering no longer counts
    assert json.loads((d / "manifest.json").read_text(encoding="utf-8"))["events"][-1]["rebuilt_at"]
    assert "answers that were the non-LLM fallback: 0" in (d / "summary.txt").read_text(encoding="utf-8")
    # the raw evidence is untouched
    raw = {r["id"]: r for r in rfe.load_jsonl(str(path))}
    assert raw["Q41"]["answer_is_fallback"] is True and raw["Q01"]["answer_check"] == "fail"
    capsys.readouterr()


def test_recompute_derived_fills_usage_totals_for_old_skipped_records():
    rec = {"kind": "multi", "id": "MT07", "outcome": "skipped", "final_query": "q", "answer": None,
           "pipeline_data": None, "llm_calls": [dict(PLANNER), dict(ANSWER)]}   # no token/cost fields, like old runs
    out = rfe.recompute_derived(rec)
    assert (out["input_tokens"], out["output_tokens"], out["llm_call_count"]) == (2300, 180, 2)
    assert out["cost_usd"] > 0
