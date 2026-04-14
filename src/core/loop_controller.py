from typing import Any, Dict, List

import pandas as pd

from src.core.planner import PlanStep
from src.core.executor import _run_step, _init_state_store
from src.core.param_fixer import fix_params
from src.core.replanner import replan


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RETRIES_PER_STEP = 2


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def run(
    planner_output: Dict[str, Any],
    df: pd.DataFrame,
    query: str,
    schema: Dict[str, Any],
    logger=None,
    run_id: str = None,
) -> Dict[str, Any]:
    """
    Orchestrates plan execution with per-step retry and replan fallback.

    Execution flow per step:
        1. Run step via _run_step
        2. On failure: call fix_params → retry (up to RETRIES_PER_STEP times)
        3. On retry exhaustion: call replanner for a full new plan
        4. On replan failure: return partial trace + explanation

    Caps total executions at len(plan) * 2 to prevent runaway retries.

    Args:
        planner_output : Full dict returned by planner.plan() with status "success".
        df             : The original raw DataFrame to execute against.
        query          : Original user query (passed to param_fixer and replanner).
        schema         : Condensed schema dict (passed to param_fixer and replanner).

    Returns:
        {
            "status":            "success" | "error",
            "final_df":          pd.DataFrame | None,
            "message":           str,
            "trace":             list of per-step trace records,
            "total_executions":  int
        }
    """
    trace: List[Dict[str, Any]] = []
    plan: List[PlanStep] = planner_output.get("plan", [])

    if not plan:
        return {
            "status":           "error",
            "final_df":         None,
            "message":          "Plan is empty. Nothing to execute.",
            "trace":            trace,
            "total_executions": 0,
        }

    max_executions = len(plan) * 2
    total_executions = 0

    # Initialise state store
    try:
        state_store = _init_state_store(df)
    except ValueError as e:
        return {
            "status":           "error",
            "final_df":         None,
            "message":          str(e),
            "trace":            trace,
            "total_executions": 0,
        }

    final_df = None

    try:
        for step in plan:

            step_succeeded = False
            current_step = step
            last_step_result: Dict[str, Any] = {}

            # ----------------------------------------------------------------
            # Attempt original run + up to RETRIES_PER_STEP retries
            # ----------------------------------------------------------------
            for attempt in range(RETRIES_PER_STEP + 1):  # 0 = original, 1 = retry 1, 2 = retry 2

                # Hard cap — prevents runaway execution across retries
                if total_executions >= max_executions:
                    return {
                        "status":           "error",
                        "final_df":         None,
                        "message":          (
                            f"Execution cap reached: {max_executions} total executions "
                            f"allowed for a {len(plan)}-step plan."
                        ),
                        "trace":            trace,
                        "total_executions": total_executions,
                    }

                last_step_result = _run_step(current_step, state_store, logger=logger, run_id=run_id)
                total_executions += 1
                trace.append(last_step_result["trace_record"])

                if last_step_result["status"] == "success":
                    state_store[current_step.output] = last_step_result["result_df"]
                    final_df = last_step_result["result_df"]
                    step_succeeded = True
                    break

                # Step failed — fix params and retry if attempts remain
                if attempt < RETRIES_PER_STEP:
                    error_context = {
                        "message":      last_step_result["message"],
                        "trace_record": last_step_result["trace_record"],
                    }
                    current_step = fix_params(current_step, error_context, query, schema)

            # ----------------------------------------------------------------
            # All attempts exhausted — try replanner
            # ----------------------------------------------------------------
            if not step_succeeded:
                error_context = {
                    "failed_step": current_step,
                    "message":     last_step_result.get("message", "Unknown error."),
                    "trace":       trace,
                }
                replan_result = replan(planner_output, error_context, query, schema)

                if replan_result.get("status") != "success":
                    return {
                        "status":           "error",
                        "final_df":         None,
                        "message":          (
                            f"Step {step.step} ({step.tool}) failed after {RETRIES_PER_STEP} "
                            f"retry attempt(s) and replan was unsuccessful. "
                            f"Last error: {last_step_result.get('message', 'Unknown error.')}"
                        ),
                        "trace":            trace,
                        "total_executions": total_executions,
                    }

                # Replan succeeded — full restart with new plan
                # Deferred: will recursively call run() with new planner_output once
                # replanner is fully implemented.
                return {
                    "status":           "error",
                    "final_df":         None,
                    "message":          "Replan restart not yet implemented.",
                    "trace":            trace,
                    "total_executions": total_executions,
                }

    except Exception as e:
        return {
            "status":           "error",
            "final_df":         None,
            "message":          f"Unexpected crash in loop controller: {type(e).__name__}: {str(e)}",
            "trace":            trace,
            "total_executions": total_executions,
        }

    return {
        "status":           "success",
        "final_df":         final_df,
        "message":          (
            f"Executed {len(plan)} step(s) successfully "
            f"({total_executions} total execution(s))."
        ),
        "trace":            trace,
        "total_executions": total_executions,
    }
