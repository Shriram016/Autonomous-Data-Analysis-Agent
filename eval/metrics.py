"""
metrics.py -- Per-case records, aggregate metrics, report generation, and result saving.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from eval.comparator import CompareResult
from eval.test_cases import EvalCase


# ---------------------------------------------------------------------------
# Per-case record
# ---------------------------------------------------------------------------

def compute_record(
    case: EvalCase,
    gt_df: Optional[pd.DataFrame],
    gt_error: bool,
    pipeline_result: Dict[str, Any],
    compare_result: Optional[CompareResult],
    duration_s: float,
) -> Dict[str, Any]:
    """Build a flat dict summarising one evaluation case."""
    plan = pipeline_result.get("plan") or []
    trace = pipeline_result.get("trace") or []
    plan_steps = len(plan)
    total_executions = pipeline_result.get("total_executions", 0)
    retries = max(0, total_executions - plan_steps)
    had_step_error = any(
        isinstance(step, dict) and step.get("status") == "error" for step in trace
    )

    if compare_result is not None:
        value_match = compare_result.value_match
        shape_match = compare_result.shape_match
        columns_match = compare_result.columns_match
        full_match = compare_result.full_match
        mismatches = compare_result.mismatches
        pipeline_shape = compare_result.pipeline_shape
    else:
        # Pipeline failed or GT failed -- no comparison possible
        value_match = False
        shape_match = None
        columns_match = None
        full_match = False
        mismatches = (
            ["GT function raised an error -- comparison skipped"]
            if gt_error
            else ["Pipeline returned no result -- comparison skipped"]
        )
        pipeline_shape = None

    gt_shape = gt_df.shape if gt_df is not None else None

    return {
        "id": case.id,
        "query": case.query,
        "tags": case.tags,
        "compare_mode": case.compare_mode,
        "notes": case.notes,
        # Pipeline outcome
        "pipeline_status": pipeline_result.get("status"),
        "pipeline_success": pipeline_result.get("final_df") is not None,
        "pipeline_message": pipeline_result.get("message", ""),
        # GT outcome
        "gt_error": gt_error,
        "gt_shape": gt_shape,
        "pipeline_shape": pipeline_shape,
        # Comparison results
        "value_match": value_match,
        "shape_match": shape_match,
        "columns_match": columns_match,
        "full_match": full_match,
        "mismatches": mismatches,
        # Execution stats
        "plan_steps": plan_steps,
        "total_executions": total_executions,
        "retries": retries,
        "had_step_error": had_step_error,
        "duration_s": round(duration_s, 2),
        # Answer
        "answer": pipeline_result.get("answer"),
        # Raw DataFrames (serialized for JSON)
        "gt_data": gt_df.to_dict(orient="records") if gt_df is not None else None,
        "pipeline_data": (
            pipeline_result["final_df"].to_dict(orient="records")
            if pipeline_result.get("final_df") is not None
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------

_GROUP_NAMES = {
    1: "Simple Aggregation",
    2: "Filtering",
    3: "Grouping + Ranking",
    4: "Time Based",
    5: "Multi Condition",
    6: "Derived Calculations",
}


def compute_aggregate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary metrics across all records."""
    n = len(records)
    if n == 0:
        return {}

    successful = [r for r in records if r["pipeline_success"] and not r["gt_error"]]
    n_success = len(successful)

    return {
        "total_queries": n,
        "pipeline_success_count": sum(1 for r in records if r["pipeline_success"]),
        "pipeline_success_rate": _pct(sum(1 for r in records if r["pipeline_success"]), n),
        "gt_error_count": sum(1 for r in records if r["gt_error"]),
        "value_match_count": sum(1 for r in successful if r["value_match"]),
        "value_match_rate": _pct(sum(1 for r in successful if r["value_match"]), n_success),
        "full_match_count": sum(1 for r in successful if r["full_match"]),
        "full_match_rate": _pct(sum(1 for r in successful if r["full_match"]), n_success),
        "avg_executions": round(sum(r["total_executions"] for r in records) / n, 1),
        "avg_retries": round(sum(r["retries"] for r in records) / n, 2),
        "avg_duration_s": round(sum(r["duration_s"] for r in records) / n, 1),
        "total_duration_s": round(sum(r["duration_s"] for r in records), 1),
        "groups": _group_metrics(records),
    }


def _group_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    groups: Dict[int, List[Dict]] = {}
    for r in records:
        qnum = int(r["id"][1:])   # "Q01" -> 1
        grp = (qnum - 1) // 5 + 1
        groups.setdefault(grp, []).append(r)

    result = {}
    for grp_num in sorted(groups):
        grp_records = groups[grp_num]
        successful = [r for r in grp_records if r["pipeline_success"] and not r["gt_error"]]
        n_grp = len(grp_records)
        n_suc = len(successful)
        result[f"Group {grp_num}"] = {
            "name": _GROUP_NAMES.get(grp_num, f"Group {grp_num}"),
            "count": n_grp,
            "pipeline_success_rate": _pct(
                sum(1 for r in grp_records if r["pipeline_success"]), n_grp
            ),
            "value_match_rate": _pct(
                sum(1 for r in successful if r["value_match"]), n_suc
            ),
            "full_match_rate": _pct(
                sum(1 for r in successful if r["full_match"]), n_suc
            ),
            "avg_retries": round(
                sum(r["retries"] for r in grp_records) / n_grp, 2
            ),
        }
    return result


def _pct(num: int, denom: int) -> float:
    return round(num / denom, 4) if denom > 0 else 0.0


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(records: List[Dict[str, Any]], aggregate: Dict[str, Any]) -> str:
    lines: List[str] = []
    w = 100

    lines.append("=" * w)
    lines.append("ADAA EVALUATION REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * w)
    lines.append("")

    # Per-case table
    header = (
        f"{'ID':<6} {'Status':<12} {'Val':^5} {'Full':^5} {'Mode':<12} "
        f"{'Exec':>5} {'Retry':>5} {'Time':>7}  Query"
    )
    lines.append(header)
    lines.append("-" * w)

    for r in records:
        status = (r["pipeline_status"] or "none")[:11]
        val = _tick(r["value_match"], r["gt_error"], r["pipeline_success"])
        full = _tick(r["full_match"], r["gt_error"], r["pipeline_success"])
        lines.append(
            f"{r['id']:<6} {status:<12} {val:^5} {full:^5} {r['compare_mode']:<12} "
            f"{r['total_executions']:>5} {r['retries']:>5} {r['duration_s']:>6.1f}s  "
            f"{r['query'][:40]}"
        )

    lines.append("-" * w)
    lines.append("")

    # Overall summary
    agg = aggregate
    n_suc = agg["pipeline_success_count"]
    lines.append(
        f"OVERALL  ({agg['total_queries']} queries | "
        f"{agg['total_duration_s']:.0f}s total | "
        f"{agg['avg_duration_s']:.1f}s avg)"
    )
    lines.append(
        f"  Pipeline success : {n_suc}/{agg['total_queries']} "
        f"({agg['pipeline_success_rate']:.0%})"
    )
    lines.append(
        f"  Value match      : {agg['value_match_count']}/{n_suc} "
        f"({agg['value_match_rate']:.0%})  [primary correctness metric]"
    )
    lines.append(
        f"  Full match       : {agg['full_match_count']}/{n_suc} "
        f"({agg['full_match_rate']:.0%})  [shape + columns + values]"
    )
    lines.append(
        f"  Avg executions   : {agg['avg_executions']:.1f}"
    )
    lines.append(
        f"  Avg retries      : {agg['avg_retries']:.2f}"
    )
    if agg.get("gt_error_count", 0) > 0:
        lines.append(
            f"  GT errors        : {agg['gt_error_count']} (excluded from match rates)"
        )
    lines.append("")

    # Group breakdown
    lines.append("GROUP BREAKDOWN")
    lines.append(
        f"  {'Group':<24} {'Success':>8} {'Value':>8} {'Full':>8} {'AvgRetry':>9}"
    )
    lines.append("  " + "-" * 60)
    for grp_key, grp in agg.get("groups", {}).items():
        lines.append(
            f"  {grp_key + ' ' + grp['name']:<24} "
            f"{grp['pipeline_success_rate']:>7.0%} "
            f"{grp['value_match_rate']:>8.0%} "
            f"{grp['full_match_rate']:>8.0%} "
            f"{grp['avg_retries']:>9.2f}"
        )
    lines.append("")

    # Failure detail
    failures = [
        r for r in records
        if not r["value_match"] and not r["gt_error"] and r["pipeline_success"]
    ]
    errors = [r for r in records if not r["pipeline_success"] and not r["gt_error"]]

    if errors:
        lines.append("PIPELINE ERRORS")
        for r in errors:
            lines.append(f"  {r['id']}: {r['query'][:70]}")
            lines.append(f"    status={r['pipeline_status']}  msg={r['pipeline_message'][:80]}")
        lines.append("")

    if failures:
        lines.append("VALUE MISMATCHES")
        for r in failures:
            lines.append(f"  {r['id']}: {r['query'][:70]}")
            lines.append(
                f"    gt_shape={r['gt_shape']}  pipeline_shape={r['pipeline_shape']}"
            )
            for m in r["mismatches"][:3]:
                lines.append(f"    -> {m}")
        lines.append("")

    lines.append("=" * w)
    return "\n".join(lines)


def _tick(match: bool, gt_error: bool, pipeline_success: bool) -> str:
    if gt_error:
        return "GT?"
    if not pipeline_success:
        return "ERR"
    return "Y" if match else "N"  # ASCII only -- avoid Windows cp1252 issues


# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------

def save_results(
    records: List[Dict[str, Any]],
    aggregate: Dict[str, Any],
    report_text: str,
    output_dir: str,
) -> tuple[str, str, str]:
    """
    Save evaluation results to three files:
        <timestamp>.json   -- full detail per case
        <timestamp>.csv    -- summary table
        <timestamp>_report.txt -- human-readable console report

    Returns (json_path, csv_path, txt_path).
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    base = os.path.join(output_dir, f"eval_{timestamp}")

    # JSON -- full detail
    json_path = f"{base}.json"
    serialisable_records = []
    for r in records:
        row = {}
        for k, v in r.items():
            if isinstance(v, tuple):
                row[k] = list(v)
            elif isinstance(v, float) and (v != v):  # NaN
                row[k] = None
            else:
                row[k] = v
        serialisable_records.append(row)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {"aggregate": aggregate, "records": serialisable_records},
            f,
            indent=2,
            default=str,
        )

    # CSV -- summary table
    csv_path = f"{base}.csv"
    csv_fields = [
        "id", "pipeline_status", "pipeline_success", "gt_error",
        "value_match", "full_match", "shape_match", "columns_match",
        "plan_steps", "total_executions", "retries", "had_step_error",
        "duration_s", "compare_mode", "gt_shape", "pipeline_shape", "query",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k) for k in csv_fields})

    # Text report
    txt_path = f"{base}_report.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    return json_path, csv_path, txt_path
