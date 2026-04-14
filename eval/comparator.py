"""
comparator.py — DataFrame comparison for eval pipeline.

Three comparison modes:
    value_only : Extract all numeric cell values from each DataFrame, sort them,
                 compare arrays with float tolerance. No shape/column checks.
                 Used for scalar-result queries where pipeline output wrapping is uncertain.

    full       : Shape match → column set match → sort both DataFrames by all columns
                 → cell-level value comparison. All three checks must pass.
                 Used for multi-row unordered results (e.g. "total per year").

    ordered    : Same as full but without pre-sorting. Row positions are compared
                 directly. Used for ranked results (top-N queries).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd


@dataclass
class CompareResult:
    mode: str
    value_match: bool
    full_match: bool
    shape_match: Optional[bool] = None       # None when mode="value_only"
    columns_match: Optional[bool] = None     # None when mode="value_only"
    mismatches: List[str] = field(default_factory=list)
    gt_shape: tuple = ()
    pipeline_shape: tuple = ()
    gt_columns: List[str] = field(default_factory=list)
    pipeline_columns: List[str] = field(default_factory=list)


def compare(
    gt_df: pd.DataFrame,
    pipeline_df: Optional[pd.DataFrame],
    mode: str = "value_only",
    float_tol: float = 0.01,
) -> CompareResult:
    """
    Compare ground truth DataFrame against pipeline output DataFrame.

    Parameters
    ----------
    gt_df        : Ground truth DataFrame produced by the test case function.
    pipeline_df  : DataFrame from pipeline final_df. May be None if pipeline failed.
    mode         : "value_only" | "full" | "ordered"
    float_tol    : Relative tolerance for numeric comparisons (default 1%).
    """
    gt_shape = gt_df.shape if gt_df is not None else (0, 0)
    pipe_shape = pipeline_df.shape if pipeline_df is not None else (0, 0)
    gt_cols = list(gt_df.columns) if gt_df is not None else []
    pipe_cols = list(pipeline_df.columns) if pipeline_df is not None else []

    if pipeline_df is None:
        return CompareResult(
            mode=mode,
            value_match=False,
            full_match=False,
            shape_match=False,
            columns_match=False,
            mismatches=["Pipeline returned None (final_df is None)"],
            gt_shape=gt_shape,
            pipeline_shape=(0, 0),
            gt_columns=gt_cols,
            pipeline_columns=[],
        )

    if mode == "value_only":
        return _compare_value_only(
            gt_df, pipeline_df, float_tol, gt_shape, pipe_shape, gt_cols, pipe_cols
        )
    elif mode in ("full", "ordered"):
        return _compare_structural(
            gt_df, pipeline_df, mode, float_tol, gt_shape, pipe_shape, gt_cols, pipe_cols
        )
    else:
        raise ValueError(f"Unknown compare mode: '{mode}'. Expected: value_only, full, ordered.")


# ---------------------------------------------------------------------------
# value_only
# ---------------------------------------------------------------------------

def _compare_value_only(
    gt_df, pipeline_df, float_tol, gt_shape, pipe_shape, gt_cols, pipe_cols
) -> CompareResult:
    gt_nums = _extract_numerics(gt_df)
    pipe_nums = _extract_numerics(pipeline_df)

    mismatches: List[str] = []

    if len(gt_nums) == 0:
        return CompareResult(
            mode="value_only",
            value_match=False,
            full_match=False,
            mismatches=["GT has no numeric columns — check ground truth function"],
            gt_shape=gt_shape,
            pipeline_shape=pipe_shape,
            gt_columns=gt_cols,
            pipeline_columns=pipe_cols,
        )

    if len(pipe_nums) == 0:
        return CompareResult(
            mode="value_only",
            value_match=False,
            full_match=False,
            mismatches=["Pipeline output has no numeric columns"],
            gt_shape=gt_shape,
            pipeline_shape=pipe_shape,
            gt_columns=gt_cols,
            pipeline_columns=pipe_cols,
        )

    if len(gt_nums) != len(pipe_nums):
        mismatches.append(
            f"Numeric value count mismatch: GT has {len(gt_nums)} value(s), "
            f"pipeline has {len(pipe_nums)} value(s). "
            f"GT shape={gt_shape}, pipeline shape={pipe_shape}."
        )
        value_match = False
    else:
        gt_sorted = np.sort(gt_nums)
        pipe_sorted = np.sort(pipe_nums)
        for i, (g, p) in enumerate(zip(gt_sorted, pipe_sorted)):
            if np.isnan(g) and np.isnan(p):
                continue
            if np.isnan(g) or np.isnan(p):
                mismatches.append(f"Value[{i}]: GT={g}, Pipeline={p} (NaN mismatch)")
            elif not _is_close(g, p, float_tol):
                rel_diff = abs(g - p) / max(abs(g), 1e-10)
                mismatches.append(
                    f"Value[{i}]: GT={g:.4f}, Pipeline={p:.4f}, diff={rel_diff:.2%}"
                )
        value_match = len(mismatches) == 0

    return CompareResult(
        mode="value_only",
        value_match=value_match,
        full_match=value_match,
        mismatches=mismatches,
        gt_shape=gt_shape,
        pipeline_shape=pipe_shape,
        gt_columns=gt_cols,
        pipeline_columns=pipe_cols,
    )


# ---------------------------------------------------------------------------
# full / ordered
# ---------------------------------------------------------------------------

def _compare_structural(
    gt_df, pipeline_df, mode, float_tol, gt_shape, pipe_shape, gt_cols, pipe_cols
) -> CompareResult:
    mismatches: List[str] = []

    # 1. Shape check
    shape_match = gt_shape == pipe_shape
    if not shape_match:
        mismatches.append(
            f"Shape mismatch: GT={gt_shape}, Pipeline={pipe_shape}"
        )

    # 2. Column set check
    gt_col_set = set(gt_df.columns)
    pipe_col_set = set(pipeline_df.columns)
    columns_match = gt_col_set == pipe_col_set
    if not columns_match:
        extra = sorted(pipe_col_set - gt_col_set)
        missing = sorted(gt_col_set - pipe_col_set)
        if extra:
            mismatches.append(f"Unexpected columns in pipeline output: {extra}")
        if missing:
            mismatches.append(f"Missing columns from pipeline output: {missing}")

    # Early exit if shape or columns fail — value comparison is meaningless
    if not shape_match or not columns_match:
        return CompareResult(
            mode=mode,
            value_match=False,
            full_match=False,
            shape_match=shape_match,
            columns_match=columns_match,
            mismatches=mismatches,
            gt_shape=gt_shape,
            pipeline_shape=pipe_shape,
            gt_columns=gt_cols,
            pipeline_columns=pipe_cols,
        )

    # 3. Align column order to match GT
    pipeline_aligned = pipeline_df[gt_df.columns]

    # 4. Sort both DataFrames if unordered comparison
    if mode == "full":
        try:
            sort_cols = list(gt_df.columns)
            gt_cmp = (
                gt_df.sort_values(sort_cols, key=lambda s: s.astype(str))
                .reset_index(drop=True)
            )
            pipe_cmp = (
                pipeline_aligned.sort_values(sort_cols, key=lambda s: s.astype(str))
                .reset_index(drop=True)
            )
        except Exception as exc:
            mismatches.append(f"Failed to sort DataFrames for comparison: {exc}")
            return CompareResult(
                mode=mode,
                value_match=False,
                full_match=False,
                shape_match=shape_match,
                columns_match=columns_match,
                mismatches=mismatches,
                gt_shape=gt_shape,
                pipeline_shape=pipe_shape,
                gt_columns=gt_cols,
                pipeline_columns=pipe_cols,
            )
    else:  # ordered — compare rows as-is
        gt_cmp = gt_df.reset_index(drop=True)
        pipe_cmp = pipeline_aligned.reset_index(drop=True)

    # 5. Cell-level value comparison
    value_mismatches = _compare_values(gt_cmp, pipe_cmp, float_tol)
    mismatches.extend(value_mismatches)
    value_match = len(value_mismatches) == 0

    return CompareResult(
        mode=mode,
        value_match=value_match,
        full_match=value_match,   # shape + columns already confirmed above
        shape_match=shape_match,
        columns_match=columns_match,
        mismatches=mismatches,
        gt_shape=gt_shape,
        pipeline_shape=pipe_shape,
        gt_columns=gt_cols,
        pipeline_columns=pipe_cols,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compare_values(
    gt_df: pd.DataFrame, pipe_df: pd.DataFrame, float_tol: float
) -> List[str]:
    """Cell-level comparison between two aligned DataFrames of identical shape."""
    mismatches: List[str] = []
    max_reported = 5

    for col in gt_df.columns:
        if len(mismatches) >= max_reported:
            mismatches.append("... (further mismatches truncated)")
            break

        gt_col = gt_df[col]
        pipe_col = pipe_df[col]

        if pd.api.types.is_numeric_dtype(gt_col):
            for i, (g, p) in enumerate(zip(gt_col, pipe_col)):
                if pd.isna(g) and pd.isna(p):
                    continue
                if pd.isna(g) or pd.isna(p):
                    mismatches.append(
                        f"Row {i}, col '{col}': GT={g}, Pipeline={p} (NaN mismatch)"
                    )
                elif not _is_close(float(g), float(p), float_tol):
                    rel = abs(g - p) / max(abs(g), 1e-10)
                    mismatches.append(
                        f"Row {i}, col '{col}': GT={g:.4f}, Pipeline={p:.4f}, diff={rel:.2%}"
                    )
                if len(mismatches) >= max_reported:
                    break
        else:
            for i, (g, p) in enumerate(zip(gt_col, pipe_col)):
                gs = str(g).strip().lower() if not pd.isna(g) else ""
                ps = str(p).strip().lower() if not pd.isna(p) else ""
                if gs != ps:
                    mismatches.append(
                        f"Row {i}, col '{col}': GT='{g}', Pipeline='{p}'"
                    )
                if len(mismatches) >= max_reported:
                    break

    return mismatches


def _extract_numerics(df: pd.DataFrame) -> np.ndarray:
    """Return all numeric cell values from df as a 1-D float array."""
    numeric_df = df.select_dtypes(include="number")
    return numeric_df.values.flatten().astype(float)


def _is_close(a: float, b: float, tol: float) -> bool:
    """Relative tolerance comparison. Falls back to absolute for near-zero values."""
    denom = max(abs(a), abs(b), 1e-10)
    return abs(a - b) / denom <= tol
