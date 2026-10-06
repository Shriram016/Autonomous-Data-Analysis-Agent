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


def _run_case(case: MultiTurnEvalCase, df: pd.DataFrame, verbose: bool) -> Dict[str, Any]:
    """Run every turn of a case sequentially under one session_id, check the final turn."""

    session_id = str(uuid.uuid4())
    context_turns = case.turns[:-1]
    final_turn = case.turns[-1]

    start = time.perf_counter()
    pipeline_result: Dict[str, Any] = {}
    skip_reason: str | None = None

    # Run context-setting turns; skip the whole case if any of them error.
    for turn in context_turns:
        try:
            result = run_pipeline(turn.query, session_id=session_id)
        except Exception as exc:
            skip_reason = f"Turn '{turn.query[:40]}' raised: {exc}"
            break

        if result.get("status") == "error":
            skip_reason = (
                f"Turn '{turn.query[:40]}' returned status=error: "
                f"{result.get('message', '')}"
            )
            break

        time.sleep(_TURN_DELAY_S)

    # Run the final (evaluated) turn only if no context turn failed.
    if skip_reason is None:
        try:
            pipeline_result = run_pipeline(final_turn.query, session_id=session_id)
        except Exception as exc:
            pipeline_result = {"status": "error", "final_df": None, "message": str(exc)}

    duration = time.perf_counter() - start

    # --- Skipped case ---
    if skip_reason is not None:
        record = {
            "id": case.id,
            "tags": case.tags,
            "num_turns": len(case.turns),
            "final_query": final_turn.query,
            "outcome": "skipped",
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
        "pipeline_status": pipeline_result.get("status"),
        "value_match": value_match,
        "mismatches": mismatches,
        "duration_s": round(duration, 2),
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
) -> List[Dict[str, Any]]:
    print("=" * 70)
    print("ADAA Multi-Turn Evaluation (Session Memory)")
    print("=" * 70)

    print(f"Loading dataset from: {_DATA_PATH}")
    df = _load_dataset()
    print(f"Dataset loaded: {len(df):,} rows x {len(df.columns)} columns\n")

    cases = MULTITURN_TEST_CASES
    if ids:
        id_set = set(ids)
        cases = [c for c in cases if c.id in id_set]
        print(f"Running subset: {[c.id for c in cases]}\n")

    records: List[Dict[str, Any]] = []
    for case in cases:
        records.append(_run_case(case, df, verbose))

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
    args = parser.parse_args()

    ids = args.ids.split(",") if args.ids else None
    records = run_multiturn_eval(verbose=True, ids=ids)

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
