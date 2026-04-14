from typing import Any, Dict, List

import pandas as pd

from src.tools.tools import TOOL_REGISTRY
from src.core.planner import PlanStep
from src.critics.rule_based_critic import critique


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORIGINAL_DF_KEY = "original_df"


# ---------------------------------------------------------------------------
# Component 1 — State Store Initialiser
# ---------------------------------------------------------------------------

def _init_state_store(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Initialises the state store for a single execution run.

    Validates that the input DataFrame is not None and not empty before
    storing it. The state store is a dict keyed by step output names,
    used by the Step Runner to pass DataFrames between steps.

    Args:
        df: The original raw DataFrame to begin execution with.

    Returns:
        {"original_df": df}

    Raises:
        ValueError: If df is None or empty.
    """
    if df is None:
        raise ValueError("Input DataFrame is None. Cannot initialise state store.")

    if df.empty:
        raise ValueError("Input DataFrame is empty. Cannot initialise state store.")

    return {ORIGINAL_DF_KEY: df}


# ---------------------------------------------------------------------------
# Component 2 — Tool Caller
# ---------------------------------------------------------------------------

def _call_tool(
    step: PlanStep,
    input_df: pd.DataFrame,
    logger=None,
    run_id: str = None,
) -> Dict[str, Any]:
    """
    Calls the tool specified in the plan step with the given DataFrame.

    Fetches the tool function from TOOL_REGISTRY, injects the input DataFrame,
    and merges with the step's parameters before calling.

    Logs tool_call_started (params) and tool_call_completed (shape) if a
    logger is provided.

    Returns the tool's standard response dict on success, or a standard error
    dict if the tool is not found, the result is None, or the tool crashes.

    Args:
        step     : The PlanStep containing tool name and parameters.
        input_df : The DataFrame to pass as the df argument to the tool.
        logger   : Optional logger instance for per-tool logging.
        run_id   : Run identifier passed to log_event.

    Returns:
        {"status": "success|error", "message": str, "result": pd.DataFrame | None}
    """
    from src.utils.logger import log_event

    # Defensive check — tool should already be validated by _validate_plan()
    if step.tool not in TOOL_REGISTRY:
        return {
            "status": "error",
            "message": f"Tool '{step.tool}' not found in TOOL_REGISTRY.",
            "result": None,
        }

    tool_fn = TOOL_REGISTRY[step.tool]
    args = {"df": input_df, **step.parameters}

    # Log before tool call — tool name + input shape + params
    if logger and run_id:
        log_event(logger, run_id, "tool_call_started", {
            "step":        step.step,
            "tool":        step.tool,
            "input_shape": tuple(input_df.shape),
            "parameters":  step.parameters,
        })

    try:
        response = tool_fn(**args)
    except Exception as e:
        response = {
            "status": "error",
            "message": f"Tool '{step.tool}' raised an unexpected error: {str(e)}",
            "result": None,
        }

    # Log after tool call — status + output shape
    if logger and run_id:
        result_df = response.get("result")
        log_event(logger, run_id, "tool_call_completed", {
            "step":         step.step,
            "tool":         step.tool,
            "status":       response.get("status"),
            "message":      response.get("message"),
            "output_shape": tuple(result_df.shape) if result_df is not None else None,
        })

    # Treat None result as an error even if tool reports success
    if response.get("result") is None and response.get("status") != "error":
        return {
            "status": "error",
            "message": (
                response.get("message")
                or f"Tool '{step.tool}' returned None result with no message."
            ),
            "result": None,
        }

    return response


# ---------------------------------------------------------------------------
# Component 3 — Critic
# ---------------------------------------------------------------------------
# Thin wrapper so the rest of the Executor calls a local name (_critic)
# while the real logic lives in src/critics/rule_based_critic.py.

def _critic(
    step: PlanStep,
    tool_response: Dict[str, Any],
    result_df: pd.DataFrame,
    input_df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Delegates to the Rule-Based Critic for deterministic post-step validation.

    Args:
        step          : The PlanStep that was just executed.
        tool_response : The raw response dict returned by the tool.
        result_df     : The output DataFrame from the tool (None if tool errored).
        input_df      : The DataFrame that was passed into the tool.

    Returns:
        {"status": "pass"} or {"status": "fail", "check": str, "reason": str}
    """
    return critique(step, tool_response, result_df, input_df)


# ---------------------------------------------------------------------------
# Component 4 — Trace Record Builder
# ---------------------------------------------------------------------------

def _build_trace_record(
    step: PlanStep,
    tool_response: Dict[str, Any],
    critic_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Builds a single trace record for a completed step.

    Captures step metadata, tool execution result, output DataFrame shape
    and columns, and critic verdict. Records are collected across all steps
    and returned as the execution trace.

    Args:
        step          : The PlanStep that was executed.
        tool_response : The raw response dict returned by the tool.
        critic_result : The result dict returned by the critic.

    Returns:
        A dict with step, tool, parameters, status, message,
        output_shape, output_columns, and critic fields.
    """
    result_df = tool_response.get("result")

    return {
        "step":            step.step,
        "tool":            step.tool,
        "parameters":      step.parameters,
        "status":          tool_response.get("status"),
        "message":         tool_response.get("message"),
        "output_shape":    tuple(result_df.shape) if result_df is not None else None,
        "output_columns":  list(result_df.columns) if result_df is not None else None,
        "critic":          critic_result.get("status"),
    }


# ---------------------------------------------------------------------------
# Component 5 — Step Runner
# ---------------------------------------------------------------------------

def _run_step(
    step: PlanStep,
    state_store: Dict[str, pd.DataFrame],
    logger=None,
    run_id: str = None,
) -> Dict[str, Any]:
    """
    Executes a single plan step against the current state store.

    Fetches the input DataFrame from the state store, calls the tool,
    runs the critic, and builds a trace record — regardless of success or failure.
    Does NOT mutate the state store; the caller (execute) handles that.

    Args:
        step        : The PlanStep to execute.
        state_store : Current state store dict keyed by step output names.

    Returns:
        {
            "status":       "success" | "error",
            "message":      str,
            "result_df":    pd.DataFrame | None,
            "trace_record": dict
        }
    """
    # Fetch input df from state store
    if step.input not in state_store:
        trace_record = _build_trace_record(
            step,
            {"status": "error", "message": f"State store key '{step.input}' not found.", "result": None},
            {"status": "fail"},
        )
        return {
            "status":       "error",
            "message":      f"State store key '{step.input}' not found.",
            "result_df":    None,
            "trace_record": trace_record,
        }

    input_df = state_store[step.input]

    try:
        # Call tool
        tool_response = _call_tool(step, input_df, logger=logger, run_id=run_id)
        result_df = tool_response.get("result")

        # Call critic — even if tool errored, so the failure is captured in trace
        critic_result = _critic(step, tool_response, result_df, input_df)

        # Build trace record
        trace_record = _build_trace_record(step, tool_response, critic_result)

        # Tool error — return after trace is built
        if tool_response.get("status") == "error":
            return {
                "status":       "error",
                "message":      tool_response.get("message"),
                "result_df":    None,
                "trace_record": trace_record,
            }

        # Critic fail — return after trace is built
        if critic_result.get("status") == "fail":
            return {
                "status":       "error",
                "message":      f"Critic failed on step {step.step} ({step.tool}): {critic_result.get('reason', 'No reason provided.')}",
                "result_df":    None,
                "trace_record": trace_record,
            }

        return {
            "status":       "success",
            "message":      tool_response.get("message"),
            "result_df":    result_df,
            "trace_record": trace_record,
        }

    except Exception as e:
        msg = f"Unexpected crash in step {step.step} ({step.tool}): {type(e).__name__}: {str(e)}"
        trace_record = _build_trace_record(
            step,
            {"status": "error", "message": msg, "result": None},
            {"status": "fail"},
        )
        return {
            "status":       "error",
            "message":      msg,
            "result_df":    None,
            "trace_record": trace_record,
        }


# ---------------------------------------------------------------------------
# Component 6 — Main Execute Function
# ---------------------------------------------------------------------------

def execute(planner_output: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
    """
    Executes a validated plan against the original DataFrame.

    Accepts the full planner output dict, extracts the plan steps, initialises
    the state store, and runs each step sequentially via _run_step. Stops
    immediately on any failure and returns a partial trace.

    Args:
        planner_output : Full dict returned by planner.plan() with status "success".
        df             : The original raw DataFrame to execute the plan against.

    Returns:
        {
            "status":   "success" | "error",
            "final_df": pd.DataFrame | None,
            "message":  str,
            "trace":    list of per-step trace records
        }
    """
    trace: List[Dict[str, Any]] = []

    # Extract plan from planner output
    plan: List[PlanStep] = planner_output.get("plan", [])

    if not plan:
        return {
            "status":   "error",
            "final_df": None,
            "message":  "Plan is empty. Nothing to execute.",
            "trace":    trace,
        }

    # Initialise state store
    try:
        state_store = _init_state_store(df)
    except ValueError as e:
        return {
            "status":   "error",
            "final_df": None,
            "message":  str(e),
            "trace":    trace,
        }

    # Execute each step sequentially
    final_df = None
    for step in plan:
        step_result = _run_step(step, state_store)
        trace.append(step_result["trace_record"])

        if step_result["status"] == "error":
            return {
                "status":   "error",
                "final_df": None,
                "message":  step_result["message"],
                "trace":    trace,
            }

        # Update state store and track final df
        state_store[step.output] = step_result["result_df"]
        final_df = step_result["result_df"]

    return {
        "status":   "success",
        "final_df": final_df,
        "message":  f"Executed {len(plan)} steps successfully.",
        "trace":    trace,
    }
