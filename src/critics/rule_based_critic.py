from typing import Any, Dict, List, Optional, Union

import pandas as pd

from src.core.planner import PlanStep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fail(check: str, reason: str) -> Dict[str, Any]:
    return {"status": "fail", "check": check, "reason": reason}


def _pass() -> Dict[str, Any]:
    return {"status": "pass"}


# ---------------------------------------------------------------------------
# Universal Checks (run for every tool)
# ---------------------------------------------------------------------------

def _check_not_none(step: PlanStep, result_df) -> Optional[Dict]:
    if result_df is None:
        return _fail(
            "not_none",
            f"Step {step.step} ({step.tool}) returned None result."
        )
    return None


def _check_not_empty(step: PlanStep, result_df: pd.DataFrame) -> Optional[Dict]:
    if result_df.empty:
        return _fail(
            "not_empty",
            f"Step {step.step} ({step.tool}) returned an empty DataFrame."
        )
    return None


def _check_no_fully_empty_columns(step: PlanStep, result_df: pd.DataFrame) -> Optional[Dict]:
    fully_empty = [col for col in result_df.columns if result_df[col].isnull().all()]
    if fully_empty:
        return _fail(
            "no_fully_empty_columns",
            f"Step {step.step} ({step.tool}) produced fully-empty column(s): {fully_empty}."
        )
    return None


def _check_expected_columns(
    step: PlanStep,
    result_df: pd.DataFrame,
    input_df: pd.DataFrame,
) -> Optional[Dict]:
    """
    Derives the expected output columns for each tool from its parameters
    and the input DataFrame, then checks they are present in result_df.

    Tools that preserve schema exactly (filter, sort, top_n, date_filter):
        result columns must equal input columns.
    Tools that add a column (extract_date_part, column_arithmetic):
        result must contain all input columns + new_col_name.
    Tools that project (select_columns):
        result must contain exactly col_list.
    rename_column:
        result must contain input columns with rename_map applied.
    groupby_aggregate:
        result must contain group_col(s) + {agg_col}_{op} for each agg entry.
    """
    tool = step.tool
    params = step.parameters
    input_cols = list(input_df.columns)

    if tool in ("filter_by_condition", "date_filter", "sort", "top_n"):
        missing = [c for c in input_cols if c not in result_df.columns]
        if missing:
            return _fail(
                "expected_columns",
                f"Step {step.step} ({tool}) is missing column(s) that should be "
                f"preserved from input: {missing}."
            )

    elif tool in ("extract_date_part", "column_arithmetic"):
        new_col = params.get("new_col_name")
        missing_input = [c for c in input_cols if c not in result_df.columns]
        if missing_input:
            return _fail(
                "expected_columns",
                f"Step {step.step} ({tool}) dropped input column(s): {missing_input}."
            )
        if new_col and new_col not in result_df.columns:
            return _fail(
                "expected_columns",
                f"Step {step.step} ({tool}) did not produce expected new column '{new_col}'."
            )

    elif tool == "select_columns":
        col_list = params.get("col_list", [])
        missing = [c for c in col_list if c not in result_df.columns]
        if missing:
            return _fail(
                "expected_columns",
                f"Step {step.step} (select_columns) is missing requested column(s): {missing}."
            )

    elif tool == "rename_column":
        rename_map = params.get("rename_map", {})
        expected = [rename_map.get(c, c) for c in input_cols]
        missing = [c for c in expected if c not in result_df.columns]
        if missing:
            return _fail(
                "expected_columns",
                f"Step {step.step} (rename_column) is missing expected column(s) "
                f"after rename: {missing}."
            )

    elif tool == "groupby_aggregate":
        group_col = params.get("group_col")
        agg_col = params.get("agg_col", {})
        group_cols = [group_col] if isinstance(group_col, str) else (group_col or [])
        agg_cols = [f"{col}_{op}" for col, op in agg_col.items()]
        expected = group_cols + agg_cols
        missing = [c for c in expected if c not in result_df.columns]
        if missing:
            return _fail(
                "expected_columns",
                f"Step {step.step} (groupby_aggregate) is missing expected column(s): {missing}."
            )

    elif tool == "aggregate_column":
        new_col = params.get("new_col_name")
        if new_col and new_col not in result_df.columns:
            return _fail(
                "expected_columns",
                f"Step {step.step} (aggregate_column) did not produce expected column '{new_col}'."
            )

    return None


# ---------------------------------------------------------------------------
# Tool-Specific Checks
# ---------------------------------------------------------------------------

def _check_groupby_row_count(
    step: PlanStep,
    result_df: pd.DataFrame,
    input_df: pd.DataFrame,
) -> Optional[Dict]:
    if step.tool != "groupby_aggregate":
        return None

    group_col = step.parameters.get("group_col")
    if group_col is None:
        return None

    try:
        if isinstance(group_col, str):
            expected_rows = input_df[group_col].nunique()
        elif isinstance(group_col, list):
            expected_rows = input_df.groupby(group_col).ngroups
        else:
            return None
    except KeyError:
        return None

    if len(result_df) != expected_rows:
        return _fail(
            "groupby_row_count",
            f"Step {step.step} (groupby_aggregate) expected {expected_rows} row(s) "
            f"(unique groups in '{group_col}') but got {len(result_df)}."
        )
    return None


def _check_top_n_rows(step: PlanStep, result_df: pd.DataFrame) -> Optional[Dict]:
    if step.tool != "top_n":
        return None

    N = step.parameters.get("N")
    if N is None:
        return None
    try:
        N = int(N)
    except (ValueError, TypeError):
        return None

    if len(result_df) > N:
        return _fail(
            "top_n_rows",
            f"Step {step.step} (top_n) returned {len(result_df)} rows but N={N}."
        )
    return None


def _check_date_filter_range(step: PlanStep, result_df: pd.DataFrame) -> Optional[Dict]:
    """
    Simple check: all dates in the filtered column must be <= end_date.
    """
    if step.tool != "date_filter":
        return None

    col_name = step.parameters.get("col_name")
    end_date = step.parameters.get("end_date")

    if not col_name or not end_date or col_name not in result_df.columns:
        return None

    try:
        resolved_end = pd.to_datetime(end_date)
        result_dates = pd.to_datetime(result_df[col_name], errors="coerce")
        violations = result_dates[result_dates > resolved_end]
        if not violations.empty:
            return _fail(
                "date_filter_range",
                f"Step {step.step} (date_filter) has {len(violations)} row(s) with "
                f"'{col_name}' after end_date ({end_date})."
            )
    except Exception:
        return None

    return None


def _check_numeric_agg_columns(step: PlanStep, result_df: pd.DataFrame) -> Optional[Dict]:
    if step.tool != "groupby_aggregate":
        return None

    agg_col = step.parameters.get("agg_col", {})
    non_numeric = [
        f"{col}_{op}"
        for col, op in agg_col.items()
        if f"{col}_{op}" in result_df.columns
        and not pd.api.types.is_numeric_dtype(result_df[f"{col}_{op}"])
    ]
    if non_numeric:
        return _fail(
            "numeric_agg_columns",
            f"Step {step.step} (groupby_aggregate) expected numeric dtype for "
            f"aggregated column(s) but got non-numeric: {non_numeric}."
        )
    return None


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def critique(
    step: PlanStep,
    tool_response: Dict[str, Any],
    result_df,
    input_df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Runs deterministic checks on the output of a tool call.

    Checks run in order — first failure short-circuits the rest.
    Returns {"status": "pass"} or {"status": "fail", "check": str, "reason": str}.

    Args:
        step          : The PlanStep that was just executed.
        tool_response : The raw response dict returned by the tool.
        result_df     : The output DataFrame from the tool (None if tool errored).
        input_df      : The DataFrame that was passed into the tool.
    """
    checks = [
        # Universal — order matters: None must be first
        lambda: _check_not_none(step, result_df),
        lambda: _check_not_empty(step, result_df),
        lambda: _check_no_fully_empty_columns(step, result_df),
        lambda: _check_expected_columns(step, result_df, input_df),
        # Tool-specific
        lambda: _check_groupby_row_count(step, result_df, input_df),
        lambda: _check_top_n_rows(step, result_df),
        lambda: _check_date_filter_range(step, result_df),
        lambda: _check_numeric_agg_columns(step, result_df),
    ]

    try:
        for check in checks:
            result = check()
            if result is not None:
                return result
    except Exception as e:
        return _fail(
            "critic_crash",
            f"Rule-based critic crashed on step {step.step} ({step.tool}): "
            f"{type(e).__name__}: {str(e)}"
        )

    return _pass()
