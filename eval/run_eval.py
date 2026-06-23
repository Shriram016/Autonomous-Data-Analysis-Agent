"""
run_eval.py — Entry point for the ADAA evaluation pipeline.

Usage (from project root):
    python eval/run_eval.py

What it does:
    1. Loads the Superstore dataset once.
    2. For each of 30 EvalCases:
        a. Runs the ground_truth_fn(df) → expected DataFrame
        b. Runs run_pipeline(query) → pipeline result
        c. Compares the two DataFrames with the appropriate compare mode
        d. Records per-case metrics
    3. Computes aggregate metrics and group-level breakdowns.
    4. Prints a human-readable report to the console.
    5. Saves JSON + CSV + .txt report to eval/results/.
"""

from __future__ import annotations

import io
import os
import sys
import time

# Force UTF-8 stdout/stderr on Windows to avoid cp1252 encoding errors
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from typing import Any, Dict, List, Optional

import pandas as pd

# Ensure project root is on sys.path so src.* imports resolve correctly
_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EVAL_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.core.pipeline import run_pipeline          # noqa: E402
from eval.test_cases import TEST_CASES, EvalCase    # noqa: E402
from eval.test_cases2 import TEST_CASES_2           # noqa: E402
from eval.test_cases3 import TEST_CASES_3           # noqa: E402
from eval.comparator import compare, CompareResult  # noqa: E402
from eval.metrics import (                          # noqa: E402
    compute_record,
    compute_aggregate,
    generate_report,
    save_results,
)

_RESULTS_DIR = os.path.join(_EVAL_DIR, "results")
_DATA_PATH = os.path.join(_PROJECT_ROOT, "data", "Sample - Superstore.csv")


# ---------------------------------------------------------------------------
# Dataset loader
# ---------------------------------------------------------------------------

def _load_dataset() -> pd.DataFrame:
    if not os.path.exists(_DATA_PATH):
        raise FileNotFoundError(
            f"Dataset not found at: {_DATA_PATH}\n"
            "Place 'Sample - Superstore.csv' in the data/ directory."
        )
    return pd.read_csv(_DATA_PATH, encoding="latin-1")


# ---------------------------------------------------------------------------
# Single case runner
# ---------------------------------------------------------------------------

def _run_case(
    case: EvalCase,
    df: pd.DataFrame,
    verbose: bool,
) -> Dict[str, Any]:
    """Execute one eval case: ground truth + pipeline + comparison."""

    # 1. Ground truth
    gt_df: Optional[pd.DataFrame] = None
    gt_error = False
    if case.ground_truth_fn is not None:
        try:
            gt_df = case.ground_truth_fn(df)
        except Exception as exc:
            gt_error = True
            if verbose:
                print(f"    [GT ERROR] {exc}")

    # 2. Pipeline
    start = time.perf_counter()
    try:
        pipeline_result: Dict[str, Any] = run_pipeline(case.query)
    except Exception as exc:
        pipeline_result = {
            "status": "error",
            "message": str(exc),
            "final_df": None,
            "plan": None,
            "trace": [],
            "total_executions": 0,
            "answer": None,
            "schema": None,
        }
    duration = time.perf_counter() - start

    # 3. Compare
    compare_result: Optional[CompareResult] = None
    if gt_df is not None and pipeline_result.get("final_df") is not None:
        compare_result = compare(
            gt_df=gt_df,
            pipeline_df=pipeline_result["final_df"],
            mode=case.compare_mode,
            float_tol=case.float_tol,
        )

    # 4. Build record
    record = compute_record(
        case=case,
        gt_df=gt_df,
        gt_error=gt_error,
        pipeline_result=pipeline_result,
        compare_result=compare_result,
        duration_s=duration,
    )

    return record


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def run_eval(verbose: bool = True, cases: Optional[List[EvalCase]] = None) -> List[Dict[str, Any]]:
    """
    Run eval cases and return the list of per-case records.

    Parameters
    ----------
    verbose : Print one-line status per case while running.
    cases   : List of EvalCase objects to run. Defaults to all TEST_CASES.
    """
    if cases is None:
        cases = TEST_CASES

    print("=" * 70)
    print("ADAA Evaluation Pipeline")
    print("=" * 70)

    print(f"Loading dataset from: {_DATA_PATH}")
    df = _load_dataset()
    print(f"Dataset loaded: {len(df):,} rows × {len(df.columns)} columns\n")

    records: List[Dict[str, Any]] = []
    n = len(cases)

    for i, case in enumerate(cases, start=1):
        if verbose:
            print(f"[{i:02d}/{n}] {case.id}  {case.query[:60]}...")

        record = _run_case(case, df, verbose)
        records.append(record)

        if verbose:
            icon = _status_icon(record)
            print(
                f"       {icon} "
                f"pipeline={record['pipeline_status'] or 'none':<10}  "
                f"value_match={str(record['value_match']):<5}  "
                f"exec={record['total_executions']}  "
                f"retry={record['retries']}  "
                f"time={record['duration_s']:.1f}s"
            )
            # Print first mismatch if failed
            if not record["value_match"] and record["mismatches"]:
                print(f"       >> {record['mismatches'][0]}")

    return records


def _status_icon(record: Dict[str, Any]) -> str:
    if record["gt_error"]:
        return "?"
    if not record["pipeline_success"]:
        return "FAIL"
    return "PASS" if record["value_match"] else "FAIL"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="ADAA Evaluation Pipeline")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Run only the first N cases (e.g. --limit 5)"
    )
    parser.add_argument(
        "--round", type=int, default=1, choices=[1, 2, 3],
        help="Eval round: 1=Q01-Q30 (test_cases.py), 2=Q31-Q37 (test_cases2.py), 3=Q38-Q47 (test_cases3.py)"
    )
    args = parser.parse_args()

    source = {1: TEST_CASES, 2: TEST_CASES_2, 3: TEST_CASES_3}[args.round]
    cases = source[:args.limit] if args.limit else source
    records = run_eval(verbose=True, cases=cases)

    print("\nComputing metrics...")
    aggregate = compute_aggregate(records)
    report = generate_report(records, aggregate)

    print("\n")
    print(report)

    json_path, csv_path, txt_path = save_results(
        records=records,
        aggregate=aggregate,
        report_text=report,
        output_dir=_RESULTS_DIR,
    )
    print(f"Results saved:")
    print(f"  JSON : {json_path}")
    print(f"  CSV  : {csv_path}")
    print(f"  TXT  : {txt_path}")


if __name__ == "__main__":
    main()
