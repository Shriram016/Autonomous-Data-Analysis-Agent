"""
run_multiturn_eval.py — Multi-turn eval runner for session memory (V2 SS2).

Usage (from project root):
    python eval/run_multiturn_eval.py

What it does:
    1. Loads the Superstore dataset once.
    2. For each MultiTurnEvalCase:
        a. Generates one session_id (UUID).
        b. Runs every turn's query through run_pipeline(query, session_id=session_id)
           in order, so recent_questions carries forward via the checkpoint
           exactly as it would in a real Streamlit session.
        c. Only the FINAL turn's result is compared against its ground truth
           (earlier turns exist purely to establish context).
    3. Prints a PASS/FAIL line per case and an overall summary.
    4. Saves per-case records + summary as JSON to eval/results/.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid

# Force UTF-8 stdout/stderr on Windows to avoid cp1252 encoding errors
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

# Ensure project root is on sys.path so src.* imports resolve correctly
_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EVAL_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.core.pipeline import run_pipeline                                # noqa: E402
from eval.multiturn_test_cases import MULTITURN_TEST_CASES, MultiTurnEvalCase  # noqa: E402
from eval.comparator import compare                                       # noqa: E402
from eval.answer_check import check_answer                                # noqa: E402
from eval.metrics import llm_usage_summary, is_answer_fallback            # noqa: E402

_RESULTS_DIR = os.path.join(_EVAL_DIR, "results")
_DATA_PATH = os.path.join(_PROJECT_ROOT, "data", "Sample - Superstore.csv")

# Delay between each turn's run_pipeline() call, to stay under the Groq
# tokens-per-day rate limit when running the full suite back-to-back.
_TURN_DELAY_S = 20


def _load_dataset() -> pd.DataFrame:
    if not os.path.exists(_DATA_PATH):
        raise FileNotFoundError(
            f"Dataset not found at: {_DATA_PATH}\n"
            "Place 'Sample - Superstore.csv' in the data/ directory."
        )
    return pd.read_csv(_DATA_PATH, encoding="latin-1")


def _turn_summary(query: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Short record of one pipeline turn (what it did), kept with the case record."""
    return {
        "query": query,
        "status": result.get("status"),
        "plan_tools": [getattr(s, "tool", None) or (s.get("tool") if isinstance(s, dict) else None)
                       for s in (result.get("plan") or [])],
        "answer": result.get("answer"),
        "message": result.get("message", ""),
    }


def _run_case(
    case: MultiTurnEvalCase,
    df: pd.DataFrame,
    verbose: bool,
    turn_delay: float = _TURN_DELAY_S,
) -> Dict[str, Any]:
    """Run every turn of a case sequentially under one session_id, check the final turn."""

    session_id = str(uuid.uuid4())
    context_turns = case.turns[:-1]
    final_turn = case.turns[-1]

    start = time.perf_counter()
    pipeline_result: Dict[str, Any] = {}
    skip_reason: str | None = None
    all_llm_calls: List[Dict[str, Any]] = []  # LLM calls across every turn of the case
    turn_log: List[Dict[str, Any]] = []       # one short summary per turn that was run

    # Run context-setting turns; skip the whole case if any of them error.
    for turn in context_turns:
        try:
            result = run_pipeline(turn.query, session_id=session_id)
        except Exception as exc:
            skip_reason = f"Turn '{turn.query[:40]}' raised: {exc}"
            turn_log.append({"query": turn.query, "status": "exception", "message": str(exc)})
            break

        turn_log.append(_turn_summary(turn.query, result))
        all_llm_calls.extend(result.get("llm_calls") or [])
        if result.get("status") == "error":
            skip_reason = (
                f"Turn '{turn.query[:40]}' returned status=error: "
                f"{result.get('message', '')}"
            )
            break

        if turn_delay:
            time.sleep(turn_delay)

    # Run the final (evaluated) turn only if no context turn failed.
    if skip_reason is None:
        try:
            pipeline_result = run_pipeline(final_turn.query, session_id=session_id)
        except Exception as exc:
            pipeline_result = {"status": "error", "final_df": None, "message": str(exc)}
        all_llm_calls.extend(pipeline_result.get("llm_calls") or [])
        turn_log.append(_turn_summary(final_turn.query, pipeline_result))

    duration = time.perf_counter() - start

    # --- Skipped case ---
    if skip_reason is not None:
        record = {
            "id": case.id,
            "tags": case.tags,
            "num_turns": len(case.turns),
            "final_query": final_turn.query,
            "outcome": "skipped",
            "expected_behavior": "answer",
            "passed": False,
            "session_id": session_id,
            "turns": turn_log,
            "llm_calls": all_llm_calls,
            "pipeline_status": None,
            "value_match": None,
            "mismatches": [f"Skipped: {skip_reason}"],
            "duration_s": round(duration, 2),
        }
        if verbose:
            print(
                f"[{case.id}] SKIP  turns={len(case.turns)}  "
                f"final='{final_turn.query[:50]}'"
            )
            print(f"       >> {skip_reason}")
        return record

    # --- Compare final turn ---
    gt_df = None
    gt_error = None
    try:
        gt_df = final_turn.ground_truth_fn(df)
    except Exception as exc:
        gt_error = str(exc)

    value_match = False
    mismatches: List[str] = []

    if gt_df is not None and pipeline_result.get("final_df") is not None:
        compare_result = compare(
            gt_df=gt_df,
            pipeline_df=pipeline_result["final_df"],
            mode=final_turn.compare_mode,
            float_tol=final_turn.float_tol,
        )
        value_match = compare_result.value_match
        mismatches = compare_result.mismatches
    elif gt_error:
        mismatches = [f"Ground truth error: {gt_error}"]
    else:
        mismatches = ["Pipeline returned no final_df"]

    outcome = "pass" if value_match else "fail"
    record = {
        "id": case.id,
        "tags": case.tags,
        "num_turns": len(case.turns),
        "final_query": final_turn.query,
        "outcome": outcome,
        "expected_behavior": "answer",
        "passed": bool(value_match),
        "session_id": session_id,
        "turns": turn_log,  # what each turn did (status, plan tools, answer), for diagnosing context failures
        "pipeline_status": pipeline_result.get("status"),
        "value_match": value_match,
        "mismatches": mismatches,
        "duration_s": round(duration, 2),
        # Instrumentation for the stability report (final turn plan and answer,
        # LLM usage summed over every turn of the case)
        "plan": [s.model_dump() if hasattr(s, "model_dump") else s
                 for s in (pipeline_result.get("plan") or [])],
        "answer": pipeline_result.get("answer"),
        # Final-turn evidence, so failures can be labelled without re-running
        "gt_data": gt_df.to_dict(orient="records") if gt_df is not None else None,
        "pipeline_data": (pipeline_result["final_df"].to_dict(orient="records")
                          if pipeline_result.get("final_df") is not None else None),
        "trace": pipeline_result.get("trace") or [],
        "events": pipeline_result.get("events") or [],
        "pipeline_message": pipeline_result.get("message", ""),
        "answer_check": check_answer(
            pipeline_result.get("answer"), final_turn.query, pipeline_result.get("final_df"),
            answer_is_fallback=is_answer_fallback(all_llm_calls),
        )["verdict"],
        **llm_usage_summary(all_llm_calls),
        "llm_calls": all_llm_calls,
    }

    if verbose:
        icon = "PASS" if value_match else "FAIL"
        print(
            f"[{case.id}] {icon}  turns={len(case.turns)}  "
            f"final='{final_turn.query[:50]}'  "
            f"status={record['pipeline_status']}  time={duration:.1f}s"
        )
        if not value_match and mismatches:
            print(f"       >> {mismatches[0]}")

    return record


def run_multiturn_eval(
    verbose: bool = True,
    ids: List[str] | None = None,
    repeats: int = 1,
    turn_delay: float = _TURN_DELAY_S,
    on_record=None,
    skip=None,
) -> List[Dict[str, Any]]:
    """
    on_record : optional callback called with each finished record straight away
                (used to save results crash-safely as the run progresses).
    skip      : optional set of (case_id, repeat) pairs to leave out (used to resume).
    """
    print("=" * 70)
    print("ADAA Multi-Turn Evaluation (Session Memory)")
    print("=" * 70)

    print(f"Loading dataset from: {_DATA_PATH}")
    df = _load_dataset()
    print(f"Dataset loaded: {len(df):,} rows x {len(df.columns)} columns\n")

    cases = MULTITURN_TEST_CASES
    if ids:
        known = {c.id for c in cases}
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise ValueError(f"Unknown case id(s): {unknown}. Valid ids are MT01-MT16.")
        id_set = set(ids)
        cases = [c for c in cases if c.id in id_set]
        print(f"Running subset: {[c.id for c in cases]}\n")

    records: List[Dict[str, Any]] = []
    for rep in range(1, repeats + 1):
        if repeats > 1:
            print(f"--- Repeat {rep}/{repeats} ---")
        for case in cases:  # each _run_case starts a fresh session_id, so repeats never share memory
            if skip and (case.id, rep) in skip:
                continue
            record = _run_case(case, df, verbose, turn_delay=turn_delay)
            record["repeat"] = rep
            records.append(record)
            if on_record is not None:
                on_record(record)

    return records


def _summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(records)
    passed = sum(1 for r in records if r["outcome"] == "pass")
    skipped = sum(1 for r in records if r["outcome"] == "skipped")
    failed = total - passed - skipped
    evaluated = total - skipped
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": round(passed / evaluated, 3) if evaluated else 0.0,
    }


def _save_results(records: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(_RESULTS_DIR, f"multiturn_{timestamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "records": records}, f, indent=2)
    return path


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="ADAA Multi-Turn Evaluation")
    parser.add_argument(
        "--ids", type=str, default=None,
        help="Comma-separated case IDs to run (e.g. --ids MT09,MT10,MT12)"
    )
    parser.add_argument(
        "--repeats", type=int, default=1,
        help="Run the selected cases this many times (e.g. --repeats 3) to measure consistency"
    )
    parser.add_argument(
        "--turn-delay", type=float, default=_TURN_DELAY_S,
        help=f"Seconds to wait between context turns (default {_TURN_DELAY_S}, sized for low rate "
             "limits; use 0 on the Developer plan)"
    )
    args = parser.parse_args()

    ids = [i.strip() for i in args.ids.split(",") if i.strip()] if args.ids else None
    records = run_multiturn_eval(verbose=True, ids=ids, repeats=args.repeats, turn_delay=args.turn_delay)

    summary = _summarize(records)
    print("\n" + "=" * 70)
    print(
        f"Summary: {summary['passed']}/{summary['total']} passed "
        f"({summary['pass_rate'] * 100:.1f}%)  "
        f"skipped={summary['skipped']}"
    )
    print("=" * 70)

    path = _save_results(records, summary)
    print(f"Results saved: {path}")


if __name__ == "__main__":
    main()
