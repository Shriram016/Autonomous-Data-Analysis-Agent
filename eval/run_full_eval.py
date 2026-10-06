"""
run_full_eval.py -- One command for the full ADAA eval (all single-turn and multi-turn cases),
built so that no result is lost and every number can be traced back to what produced it.

Usage (from project root):
    python eval/run_full_eval.py --dry-run          # checks everything, no LLM calls, no cost
    python eval/run_full_eval.py                    # preflight, cost estimate, asks to confirm
    python eval/run_full_eval.py --yes              # skip the confirmation
    python eval/run_full_eval.py --repeats 3        # repeat every case 3 times
    python eval/run_full_eval.py --resume eval/results/full_<timestamp>   # continue after a crash

Everything for one run goes in one folder, eval/results/full_<timestamp>/:
    manifest.json   git commit (+ uncommitted files), models and settings, hashes of the code and
                    prompts, dataset hash, prices, command, start/end, status, totals
    records.jsonl   one line per finished case, written and flushed the moment it finishes
                    (a crash loses at most the case in progress)
    console.log     the full console output
    results.json    manifest + final record per case (written at the end)
    results.csv     one row per case, for spreadsheets
    summary.txt     pass rates, failures by kind, answer-number check, fixer/critic activity, cost

--resume re-runs only what is missing or was lost to API errors; finished cases are kept.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EVAL_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from eval.run_eval import run_eval                                    # noqa: E402
from eval.run_multiturn_eval import run_multiturn_eval, MULTITURN_TEST_CASES  # noqa: E402
from eval.test_cases import TEST_CASES                                # noqa: E402
from eval.test_cases2 import TEST_CASES_2                             # noqa: E402
from eval.test_cases3 import TEST_CASES_3                             # noqa: E402
from eval.pricing import PRICES, PRICES_AS_OF                         # noqa: E402
from eval.answer_check import check_answer                            # noqa: E402
from eval.metrics import is_answer_fallback                           # noqa: E402
from eval.stability import _is_infra_failure, compute_stability, render_report  # noqa: E402

_RESULTS_DIR = os.path.join(_EVAL_DIR, "results")
_DATA_PATH = os.path.join(_PROJECT_ROOT, "data", "Sample - Superstore.csv")

# Measured on 2026-10-06: about $0.0004 per pipeline run (planner + answer writer, gpt-oss-20b).
_COST_PER_PIPELINE_RUN = 0.0004

_CODE_FILES = [
    "src/core/planner.py", "src/core/param_fixer.py", "src/core/replanner.py",
    "src/core/answer_generator.py", "src/core/nodes.py", "src/core/graph.py",
    "src/critics/rule_based_critic.py", "src/config.py",
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _git_info() -> Dict[str, Any]:
    status = _git("status", "--porcelain", "--untracked-files=no") or ""
    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "uncommitted_tracked_files": [ln.split(None, 1)[1] for ln in status.splitlines() if ln.strip()],
    }


def _code_hashes() -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    paths = list(_CODE_FILES)
    prompts_dir = os.path.join(_PROJECT_ROOT, "src", "prompts")
    if os.path.isdir(prompts_dir):
        paths += [f"src/prompts/{n}" for n in sorted(os.listdir(prompts_dir)) if n.endswith(".py")]
    for rel in paths:
        full = os.path.join(_PROJECT_ROOT, rel)
        if os.path.exists(full):
            hashes[rel] = _sha256(full)[:16]
    return hashes


def _config_snapshot() -> Dict[str, Any]:
    from src import config
    names = ["PLANNER_MODEL", "PLANNER_TEMPERATURE", "PLANNER_MAX_TOKENS", "PARAM_FIXER_MODEL",
             "PARAM_FIXER_TEMPERATURE", "PARAM_FIXER_MAX_TOKENS", "REPLANNER_MODEL",
             "REPLANNER_TEMPERATURE", "REPLANNER_MAX_TOKENS", "ANSWER_MODEL", "MAX_RETRIES_PER_STEP"]
    return {n: getattr(config, n, None) for n in names}


def _ping_llm() -> Tuple[bool, str]:
    """One tiny real call per configured model: proves the key works and the models exist."""
    from src import config
    if not config.GROQ_API_KEY:
        return False, "GROQ_API_KEY is not set"
    try:
        from groq import Groq
        client = Groq(api_key=config.GROQ_API_KEY)
        models = sorted({config.PLANNER_MODEL, config.PARAM_FIXER_MODEL,
                         config.REPLANNER_MODEL, config.ANSWER_MODEL})
        for m in models:
            client.chat.completions.create(model=m, max_tokens=50,
                                           messages=[{"role": "user", "content": "Reply: ok"}])
        return True, f"models reachable: {', '.join(models)}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:160]}"


class _Tee:
    """Write console output to the screen and to console.log."""

    encoding = "utf-8"

    def __init__(self, *streams):
        self._streams = streams

    def write(self, s: str) -> int:
        for st in self._streams:
            st.write(s)
        return len(s)

    def flush(self) -> None:
        for st in self._streams:
            st.flush()

    def isatty(self) -> bool:
        return False


class RecordSink:
    """Append each finished record to records.jsonl and flush it to disk immediately."""

    def __init__(self, path: str, kind: str):
        self.path = path
        self.kind = kind

    def __call__(self, record: Dict[str, Any]) -> None:
        line = json.dumps({"kind": self.kind, **record}, default=str)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return records
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a half-written last line from a crash; the case will simply be re-run
    return records


def final_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the LAST record per (kind, id, repeat), in order of first appearance."""
    latest: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
    for r in records:
        latest[(r["kind"], r["id"], r.get("repeat", 1))] = r
    return list(latest.values())


def done_keys(records: List[Dict[str, Any]]) -> Set[Tuple[str, str, int]]:
    """Cases that finished properly. Cases lost to API errors are NOT done, so resume re-runs them."""
    done = set()
    for r in final_records(records):
        if r.get("passed") or not _is_infra_failure(r):
            done.add((r["kind"], r["id"], r.get("repeat", 1)))
    return done


def recompute_derived(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recompute the fields derived from the raw evidence (answer text, result table, LLM call log):
    whether the answer was a fallback, and the answer-number check. Used by --rebuild so that a
    fix to the checks never needs a new (paid) run. The raw evidence itself is never changed.
    """
    calls = rec.get("llm_calls") or []
    rec["answer_is_fallback"] = is_answer_fallback(calls)
    data = rec.get("pipeline_data")
    res = check_answer(
        rec.get("answer"), rec.get("query") or rec.get("final_query") or "",
        pd.DataFrame(data) if data else None, answer_is_fallback=rec["answer_is_fallback"],
    )
    rec["answer_check"] = res["verdict"]
    rec["answer_numbers_unsupported"] = res["unsupported"]
    rec["answer_numbers_derived"] = res["derived"]
    return rec


# ---------------------------------------------------------------------------
# Failure kinds and summary
# ---------------------------------------------------------------------------

def failure_kind(rec: Dict[str, Any]) -> str:
    if rec.get("passed"):
        return ""
    if _is_infra_failure(rec):
        return "api_error"
    if rec.get("outcome") == "skipped":
        return "skipped_context_turn"
    status = rec.get("pipeline_status")
    if rec.get("expected_behavior") == "refuse" and status != "unsolvable":
        return "answered_instead_of_refusing"
    if status == "unsolvable":
        return "refused_but_answerable"
    if status == "error":
        return "pipeline_error"
    return "wrong_result"


def _activity(rec: Dict[str, Any]) -> Dict[str, int]:
    events = rec.get("events") or []
    trace = rec.get("trace") or []
    return {
        "param_fix": sum(1 for e in events if e.get("type") == "param_fix"),
        "param_fix_effective": sum(1 for e in events if e.get("type") == "param_fix" and e.get("changed")),
        "replan": sum(1 for e in events if e.get("type") == "replan"),
        "critic_fired": sum(1 for t in trace if t.get("critic") == "fail"),
    }


def render_summary(records: List[Dict[str, Any]], manifest: Dict[str, Any]) -> str:
    lines = ["=" * 78, "ADAA FULL EVAL SUMMARY", "=" * 78,
             f"Run        : {manifest['run_id']}  (status: {manifest['status']})",
             f"Code       : {manifest['git'].get('commit', '?')[:10] if manifest['git'].get('commit') else '?'} "
             f"on {manifest['git'].get('branch')}"
             + (f"  (+{len(manifest['git']['uncommitted_tracked_files'])} uncommitted file(s))"
                if manifest["git"].get("uncommitted_tracked_files") else ""),
             f"Models     : planner/fixer/replanner {manifest['settings'].get('PLANNER_MODEL')}, "
             f"answer {manifest['settings'].get('ANSWER_MODEL')}",
             f"Repeats    : {manifest['repeats']}", ""]

    def rate(rs: List[Dict[str, Any]]) -> str:
        p = sum(1 for r in rs if r.get("passed"))
        return f"{p}/{len(rs)} ({(p / len(rs) if rs else 0):.1%})"

    single = [r for r in records if r["kind"] == "single"]
    multi = [r for r in records if r["kind"] == "multi"]
    answer = [r for r in single if r.get("expected_behavior") == "answer"]
    refuse = [r for r in single if r.get("expected_behavior") == "refuse"]
    lines += ["PASS RATE (right behaviour: correct table, or a correct refusal where no answer exists)",
              f"  All cases                       : {rate(records)}",
              f"  Single-turn, answer expected    : {rate(answer)}",
              f"  Single-turn, refusal expected   : {rate(refuse)}",
              f"  Multi-turn                      : {rate(multi)}", ""]

    fails = [r for r in records if not r.get("passed")]
    kinds: Dict[str, int] = {}
    for r in fails:
        kinds[failure_kind(r)] = kinds.get(failure_kind(r), 0) + 1
    lines.append(f"FAILURES BY KIND ({len(fails)})")
    for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {k:<32}{n}")
    for r in fails:
        rep = f" r{r['repeat']}" if manifest["repeats"] > 1 else ""
        lines.append(f"    {r['id']}{rep}: {failure_kind(r)}")
    lines.append("")

    checks: Dict[str, int] = {}
    for r in records:
        checks[r.get("answer_check", "n/a")] = checks.get(r.get("answer_check", "n/a"), 0) + 1
    fallbacks = sum(1 for r in records if is_answer_fallback(r.get("llm_calls") or []))
    lines += ["ANSWER NUMBER CHECK (are the answer's numbers in the result table?)",
              "  " + ", ".join(f"{k}: {v}" for k, v in sorted(checks.items())),
              f"  answers that were the non-LLM fallback: {fallbacks}", ""]

    act = {k: sum(_activity(r)[k] for r in records) for k in ("param_fix", "param_fix_effective", "replan", "critic_fired")}
    lines += ["REPAIR ACTIVITY",
              f"  critic failures: {act['critic_fired']}   param-fixer calls: {act['param_fix']} "
              f"(changed params: {act['param_fix_effective']})   replans: {act['replan']}", ""]

    n = max(len(records), 1)
    cost = sum(r.get("cost_usd") or 0 for r in records)
    lines += ["COST AND TIME",
              f"  LLM calls: {sum(r.get('llm_call_count') or 0 for r in records)}   "
              f"input tokens: {sum(r.get('input_tokens') or 0 for r in records):,}   "
              f"output tokens: {sum(r.get('output_tokens') or 0 for r in records):,}",
              f"  cost: ${cost:.4f} total, ${cost / n:.5f} per case (prices as of {PRICES_AS_OF})",
              f"  time: {sum(r.get('duration_s') or 0 for r in records):.0f}s total, "
              f"{sum(r.get('duration_s') or 0 for r in records) / n:.1f}s per case"]
    return "\n".join(lines)


_CSV_FIELDS = ["kind", "id", "repeat", "expected_behavior", "passed", "failure_kind", "pipeline_status",
               "answer_check", "answer_is_fallback", "llm_call_count", "input_tokens", "output_tokens",
               "cost_usd", "duration_s", "param_fix", "replan", "critic_fired"]


def write_csv(path: str, records: List[Dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        w.writeheader()
        for r in records:
            row = {k: r.get(k) for k in _CSV_FIELDS}
            row.update({"failure_kind": failure_kind(r), "repeat": r.get("repeat", 1)})
            a = _activity(r)
            row.update({"param_fix": a["param_fix"], "replan": a["replan"], "critic_fired": a["critic_fired"]})
            w.writerow(row)


def _write_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)


def _finalize(run_dir: str, manifest: Dict[str, Any], records: List[Dict[str, Any]],
              expected: Set[Tuple[str, str, int]]) -> None:
    """Write manifest, results.json, results.csv and summary.txt from the final records."""
    lost = [r for r in records if not r.get("passed") and _is_infra_failure(r)]
    missing = expected - {(r["kind"], r["id"], r.get("repeat", 1)) for r in records}
    manifest["status"] = "complete" if not lost and not missing else "incomplete"
    manifest["finished_at"] = _now()
    manifest["totals"] = {
        "records": len(records), "passed": sum(1 for r in records if r.get("passed")),
        "lost_to_api_errors": len(lost), "missing": len(missing),
        "cost_usd": round(sum(r.get("cost_usd") or 0 for r in records), 6),
    }
    _write_json(os.path.join(run_dir, "manifest.json"), manifest)
    _write_json(os.path.join(run_dir, "results.json"), {"manifest": manifest, "records": records})
    write_csv(os.path.join(run_dir, "results.csv"), records)
    summary = render_summary(records, manifest)
    if manifest["repeats"] > 1:
        summary += "\n\n" + render_report(compute_stability(records))
    with open(os.path.join(run_dir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(summary)
    print("\n" + summary)
    print(f"\nAll files saved in: {run_dir}")
    if manifest["status"] == "incomplete":
        print(f"{len(lost)} case(s) were lost to API errors and {len(missing)} are missing. "
              f"Re-run only those with: python eval/run_full_eval.py --resume \"{run_dir}\"")


def _rebuild(run_dir: str) -> int:
    """Recompute derived fields and rewrite results.json / .csv / summary.txt from records.jsonl. Free."""
    mpath = os.path.join(run_dir, "manifest.json")
    if not os.path.exists(mpath):
        print(f"Cannot rebuild: {mpath} not found")
        return 2
    manifest = json.load(open(mpath, encoding="utf-8"))
    records = [recompute_derived(r) for r in final_records(load_jsonl(os.path.join(run_dir, "records.jsonl")))]
    expected = {(r["kind"], r["id"], r.get("repeat", 1)) for r in records}
    manifest.setdefault("events", []).append(
        {"rebuilt_at": _now(), "note": "derived fields (answer_is_fallback, answer_check) recomputed from raw "
                                       "evidence with the current checks; no LLM calls"})
    _finalize(run_dir, manifest, records, expected)
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _plan(only: str, ids: Optional[List[str]]):
    single = TEST_CASES + TEST_CASES_2 + TEST_CASES_3 if only in ("both", "single") else []
    multi = list(MULTITURN_TEST_CASES) if only in ("both", "multi") else []
    if ids:
        wanted = set(ids)
        single = [c for c in single if c.id in wanted]
        multi = [c for c in multi if c.id in wanted]
        unknown = wanted - {c.id for c in single} - {c.id for c in multi}
        if unknown:
            raise ValueError(f"Unknown or filtered-out case id(s): {sorted(unknown)}")
    return single, multi


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ADAA full eval, crash-safe and self-describing")
    parser.add_argument("--repeats", type=int, default=1, help="repeat every case N times (default 1)")
    parser.add_argument("--only", choices=["both", "single", "multi"], default="both")
    parser.add_argument("--ids", type=str, default=None, help="comma-separated case ids to run (default: all)")
    parser.add_argument("--resume", type=str, default=None, help="folder of an earlier run to continue")
    parser.add_argument("--out-dir", default=_RESULTS_DIR)
    parser.add_argument("--turn-delay", type=float, default=0.0,
                        help="seconds between context turns of a multi-turn case (0 on the Developer plan)")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument("--dry-run", action="store_true", help="run every check and write the manifest, no LLM calls")
    parser.add_argument("--rebuild", type=str, default=None,
                        help="folder of a finished run: recompute derived fields and rewrite results/summary "
                             "from records.jsonl (free, no LLM calls)")
    args = parser.parse_args(argv)

    if args.rebuild:
        return _rebuild(os.path.abspath(args.rebuild))

    ids = [i.strip() for i in args.ids.split(",") if i.strip()] if args.ids else None
    single, multi = _plan(args.only, ids)

    # ---- resume: reuse the folder and its settings
    prior: List[Dict[str, Any]] = []
    manifest: Dict[str, Any] = {}
    if args.resume:
        run_dir = os.path.abspath(args.resume)
        mpath = os.path.join(run_dir, "manifest.json")
        if not os.path.exists(mpath):
            print(f"Cannot resume: {mpath} not found")
            return 2
        manifest = json.load(open(mpath, encoding="utf-8"))
        prior = load_jsonl(os.path.join(run_dir, "records.jsonl"))
        args.repeats = manifest.get("repeats", args.repeats)
    else:
        run_dir = os.path.join(os.path.abspath(args.out_dir), f"full_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}")

    done = done_keys(prior)
    skip_single = {(i, rep) for (k, i, rep) in done if k == "single"}
    skip_multi = {(i, rep) for (k, i, rep) in done if k == "multi"}
    expected = ({("single", c.id, r) for c in single for r in range(1, args.repeats + 1)}
                | {("multi", c.id, r) for c in multi for r in range(1, args.repeats + 1)})
    to_run = expected - done
    multi_turns = sum(len(c.turns) for c in multi)

    # ---- preflight (nothing is spent or written yet)
    print("PREFLIGHT")
    checks: List[Dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"check": name, "ok": ok, "detail": detail})
        print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
        return ok

    ok = check("dataset present", os.path.exists(_DATA_PATH), _DATA_PATH)
    parent = os.path.dirname(run_dir)
    os.makedirs(parent, exist_ok=True)
    try:
        probe = os.path.join(parent, ".write_test")
        open(probe, "w").write("x")
        os.remove(probe)
        ok &= check("results folder writable", True, parent)
    except OSError as e:
        ok &= check("results folder writable", False, str(e))
    git = _git_info()
    check("code version recorded", bool(git["commit"]),
          f"{(git['commit'] or '?')[:10]}" + (f", {len(git['uncommitted_tracked_files'])} uncommitted file(s)"
                                               if git["uncommitted_tracked_files"] else ", clean"))
    if args.dry_run:
        check("LLM reachable", True, "skipped in --dry-run")
    else:
        ping_ok, ping_msg = _ping_llm()
        ok &= check("LLM reachable", ping_ok, ping_msg)
    est_runs = sum(1 for k in to_run if k[0] == "single")
    est_runs += sum(len(c.turns) for c in multi
                    for r in range(1, args.repeats + 1) if ("multi", c.id, r) in to_run)
    est = est_runs * _COST_PER_PIPELINE_RUN
    print(f"  plan: {len(single)} single-turn + {len(multi)} multi-turn cases ({multi_turns} turns), "
          f"x{args.repeats} repeat(s); {len(to_run)} of {len(expected)} runs still to do")
    print(f"  estimated cost: about ${est:.3f} (about ${_COST_PER_PIPELINE_RUN} per pipeline run, "
          f"measured 2026-10-06)")
    if not ok:
        print("Preflight failed; nothing was run and nothing was written.")
        return 2
    if not to_run:
        print("Nothing left to run.")
        return 0

    if not args.dry_run and not args.yes:
        try:
            answer = input("Proceed with the real run? [y/N] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes"):
            print("Cancelled; nothing was run.")
            return 1

    # ---- manifest
    os.makedirs(run_dir, exist_ok=True)
    manifest_path = os.path.join(run_dir, "manifest.json")
    if not args.resume:
        manifest = {
            "run_id": os.path.basename(run_dir),
            "started_at": _now(),
            "command": sys.argv,
            "repeats": args.repeats,
            "only": args.only,
            "turn_delay_s": args.turn_delay,
            "git": git,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "settings": _config_snapshot(),
            "code_hashes": _code_hashes(),
            "dataset": {"path": os.path.relpath(_DATA_PATH, _PROJECT_ROOT), "sha256": _sha256(_DATA_PATH)}
                       if os.path.exists(_DATA_PATH) else None,
            "prices": {"as_of": PRICES_AS_OF, "usd_per_1m_tokens_in_out_verified": PRICES},
            "plan": {"single_cases": len(single), "multi_cases": len(multi), "runs_expected": len(expected)},
            "preflight": checks,
            "events": [],
        }
    else:
        manifest.setdefault("events", []).append(
            {"resumed_at": _now(), "already_done": len(done), "to_run": len(to_run), "git": git})
    manifest["status"] = "dry_run" if args.dry_run else "running"
    _write_json(manifest_path, manifest)
    print(f"Run folder: {run_dir}")
    if args.dry_run:
        print("Dry run complete: manifest written, no LLM calls made.")
        return 0

    # ---- run, with the console mirrored to console.log
    records_path = os.path.join(run_dir, "records.jsonl")
    log = open(os.path.join(run_dir, "console.log"), "a", encoding="utf-8")
    real_stdout = sys.stdout
    sys.stdout = _Tee(real_stdout, log)
    started = time.perf_counter()
    try:
        try:
            if single:
                run_eval(verbose=True, cases=single, repeats=args.repeats,
                         on_record=RecordSink(records_path, "single"), skip=skip_single)
            if multi:
                run_multiturn_eval(verbose=True, ids=[c.id for c in multi], repeats=args.repeats,
                                   turn_delay=args.turn_delay,
                                   on_record=RecordSink(records_path, "multi"), skip=skip_multi)
        except BaseException as exc:  # crash, Ctrl+C: keep what was saved and say how to continue
            manifest["status"] = "interrupted"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            _write_json(manifest_path, manifest)
            print(f"\nRun interrupted ({type(exc).__name__}). {len(load_jsonl(records_path))} record(s) are saved.")
            print(f"Continue with: python eval/run_full_eval.py --resume \"{run_dir}\"")
            raise

        # ---- finalize
        records = [recompute_derived(r) for r in final_records(load_jsonl(records_path))]
        manifest["wall_clock_s"] = round(time.perf_counter() - started, 1)
        _finalize(run_dir, manifest, records, expected)
        return 0
    finally:
        sys.stdout = real_stdout
        log.close()


if __name__ == "__main__":
    sys.exit(main())
