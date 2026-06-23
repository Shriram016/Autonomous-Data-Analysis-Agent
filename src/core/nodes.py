"""
LangGraph node wrappers — V2 adapter layer.

Each function here takes the full PipelineState, reads what it needs,
calls the existing (framework-agnostic) core logic, and returns a small
dict containing only the state fields it updates. LangGraph merges that
dict back into the shared state.

Core logic is unchanged and lives in:
    - src/core/schema_gen.py      (generate_schema)
    - src/core/planner.py         (plan)
    - src/core/answer_generator.py (generate_answer)
"""

from typing import Any, Dict

import pandas as pd

from src.core.state import PipelineState
from src.core.schema_gen import generate_schema
from src.core.planner import plan
from src.core.executor import _run_step
from src.core.param_fixer import fix_params
from src.core.replanner import replan
from src.core.answer_generator import generate_answer
from src.utils.data_loader import DATE_COLUMNS
from src.utils.logger import get_logger, log_event
from src.utils.langfuse_helper import tool_span


# ---------------------------------------------------------------------------
# Schema Generator Node
# ---------------------------------------------------------------------------

def schema_gen_node(state: PipelineState) -> Dict[str, Any]:
    """
    Wraps generate_schema(). Reads `original_df` from state, writes `schema`.

    On failure, sets `status="error"` + `message` so downstream conditional
    edges (Step 4) can route to END.
    """
    run_id = state["run_id"]
    logger = get_logger(run_id)
    df = state["original_df"]

    log_event(logger, run_id, "schema_gen_started", {
        "rows": len(df),
        "cols": len(df.columns),
    })

    result = generate_schema(df, required_date_columns=DATE_COLUMNS)

    if result["status"] == "error":
        msg = f"Schema generation failed: {result['message']}"
        log_event(logger, run_id, "schema_gen_failed", {"message": msg})
        return {"status": "error", "message": msg}

    schema = result["result"]
    log_event(logger, run_id, "schema_gen_completed", {
        "column_count": len(schema),
        "columns": list(schema.keys()),
    })

    return {"schema": schema}


# ---------------------------------------------------------------------------
# Planner Node
# ---------------------------------------------------------------------------

def planner_node(state: PipelineState) -> Dict[str, Any]:
    """
    Wraps plan(). Reads `query` + `schema` from state, writes `plan` +
    `max_executions`.

    Also reads `recent_questions`, appends the current `query`, trims to the
    last 3 (oldest first, most recent last), and writes it back so the caller
    can thread it into the next query's session memory.

    On error/unsolvable, sets `status` + `message`, and `plan=[]`,
    `max_executions=0` so downstream conditional edges (Step 4) can route
    to END.
    """
    run_id = state["run_id"]
    logger = get_logger(run_id)
    query = state["query"]
    schema = state["schema"]

    previous_questions = state.get("recent_questions") or []
    recent_questions = (previous_questions + [query])[-3:]

    log_event(logger, run_id, "planner_started", {"query": query})

    result = plan(query, schema, recent_questions=previous_questions, logger=logger, run_id=run_id, session_id=state["session_id"])

    if result["status"] == "error":
        msg = f"Planner failed: {result['message']}"
        log_event(logger, run_id, "planner_failed", {"message": msg})
        return {"status": "error", "message": msg, "plan": [], "max_executions": 0, "recent_questions": recent_questions}

    if result["status"] == "unsolvable":
        reason = result["reason"]
        log_event(logger, run_id, "planner_unsolvable", {"reason": reason})
        return {
            "status": "unsolvable",
            "message": f"Query cannot be answered with available tools: {reason}",
            "plan": [],
            "max_executions": 0,
            "recent_questions": recent_questions,
        }

    plan_steps = result["plan"]
    max_executions = len(plan_steps) * 2

    log_event(logger, run_id, "planner_completed", {
        "step_count": len(plan_steps),
        "plan_summary": " -> ".join(s.tool for s in plan_steps),
        "steps": [
            {"step": s.step, "tool": s.tool, "parameters": s.parameters}
            for s in plan_steps
        ],
    })

    return {"plan": plan_steps, "max_executions": max_executions, "recent_questions": recent_questions}


# ---------------------------------------------------------------------------
# Execute Step Node
# ---------------------------------------------------------------------------

def execute_step_node(state: PipelineState) -> Dict[str, Any]:
    """
    Wraps _run_step(). Runs ONE step of the plan per invocation (the step at
    `current_step_index`), reads `plan` + `state_store` from state, and
    writes back updated `state_store`, `trace`, `total_executions`.

    The rule-based critic runs inline inside _run_step() — no separate node.

    On success:
        - Stores the step's output DataFrame in `state_store` under
          `step.output` and as `final_df`.
        - Advances `current_step_index` by 1 and resets `retry_count` to 0.
        - Sets `status="running"` (clears any error left over from a
          previous failed attempt of this same step).

    On failure:
        - `current_step_index` and `state_store` are left unchanged, so a
          retry (after param_fixer_node, Step 5) re-runs the same step.
        - Sets `status="error"` + `message` for the conditional edge
          (Step 4) to inspect.

    `trace` and `state_store` are returned as new objects (not mutated in
    place), since PipelineState fields are overwritten rather than merged.
    """
    run_id = state["run_id"]
    logger = get_logger(run_id)
    plan_steps = state["plan"]
    idx = state["current_step_index"]

    if idx >= len(plan_steps):
        msg = f"current_step_index ({idx}) out of range for plan with {len(plan_steps)} step(s)."
        log_event(logger, run_id, "execute_step_failed", {"message": msg})
        return {"status": "error", "message": msg}

    step = plan_steps[idx]
    state_store = state["state_store"]

    log_event(logger, run_id, "execute_step_started", {
        "step": step.step,
        "tool": step.tool,
        "parameters": step.parameters,
    })

    with tool_span(
        name=f"tool:{step.tool}",
        input_data={"step": step.step, "tool": step.tool, "parameters": step.parameters},
        run_id=run_id,
        session_id=state.get("session_id"),
    ) as span:
        step_result = _run_step(step, state_store, logger=logger, run_id=run_id)
        new_trace = state["trace"] + [step_result["trace_record"]]
        new_total_executions = state["total_executions"] + 1

        if step_result["status"] == "success":
            result_df = step_result["result_df"]
            log_event(logger, run_id, "execute_step_completed", {
                "step": step.step,
                "tool": step.tool,
                "output_shape": tuple(result_df.shape),
            })
            return {
                "state_store": {**state_store, step.output: result_df},
                "trace": new_trace,
                "total_executions": new_total_executions,
                "final_df": result_df,
                "current_step_index": idx + 1,
                "retry_count": 0,
                "status": "running",
                "message": "",
            }

        span.error(step_result["message"])
        log_event(logger, run_id, "execute_step_failed", {
            "step": step.step,
            "tool": step.tool,
            "message": step_result["message"],
        })
    return {
        "trace": new_trace,
        "total_executions": new_total_executions,
        "status": "error",
        "message": step_result["message"],
    }


# ---------------------------------------------------------------------------
# Param Fixer Node
# ---------------------------------------------------------------------------

def param_fixer_node(state: PipelineState) -> Dict[str, Any]:
    """
    Wraps fix_params(). Reads the failed step (`plan[current_step_index]`)
    and the error from the last execute_step_node attempt, writes a
    corrected `plan` and increments `retry_count`.

    fix_params() calls an LLM to correct the step's parameters, falling back
    to the step unchanged if the LLM call fails or the correction is still
    invalid after one retry. Clears `status`/`message` so the retried
    execute_step_node starts clean.
    """
    run_id = state["run_id"]
    logger = get_logger(run_id)
    idx = state["current_step_index"]
    step = state["plan"][idx]

    input_df = state["state_store"].get(step.input)
    current_columns = (
        {col: str(dtype) for col, dtype in input_df.dtypes.items()}
        if input_df is not None else {}
    )

    error_context = {
        "message": state["message"],
        "trace_record": state["trace"][-1] if state["trace"] else {},
        "current_columns": current_columns,
    }

    log_event(logger, run_id, "param_fixer_started", {
        "step": step.step,
        "tool": step.tool,
        "message": state["message"],
    })

    fixed_step = fix_params(step, error_context, state["query"], state["schema"], logger=logger, run_id=run_id, session_id=state["session_id"])

    new_plan = list(state["plan"])
    new_plan[idx] = fixed_step

    log_event(logger, run_id, "param_fixer_completed", {
        "step": fixed_step.step,
        "tool": fixed_step.tool,
        "parameters": fixed_step.parameters,
    })

    return {
        "plan": new_plan,
        "retry_count": state["retry_count"] + 1,
        "status": "running",
        "message": "",
    }


# ---------------------------------------------------------------------------
# Replanner Node
# ---------------------------------------------------------------------------

def replanner_node(state: PipelineState) -> Dict[str, Any]:
    """
    Wraps replan(). Reads the failed step + error context + full trace so
    far, asks for a completely new plan.

    On success: writes the new `plan`, resets `current_step_index`,
    `retry_count`, and `state_store` (back to just `original_df`) so
    execute_step_node restarts cleanly, and recomputes `max_executions`.

    On failure: sets `status="error"` + `message` so the conditional edge
    (Step 4) routes to END.

    replan() is currently a stub that always returns an error, so the
    success path is exercised only by hand-built states until Step 6
    implements it as an LLM node.
    """
    run_id = state["run_id"]
    logger = get_logger(run_id)
    idx = state["current_step_index"]
    failed_step = state["plan"][idx]

    error_context = {
        "failed_step": failed_step,
        "message": state["message"],
        "trace": state["trace"],
    }
    planner_output = {"status": "success", "plan": state["plan"]}

    log_event(logger, run_id, "replanner_started", {
        "failed_step": failed_step.step,
        "tool": failed_step.tool,
        "message": state["message"],
    })

    result = replan(planner_output, error_context, state["query"], state["schema"], logger=logger, run_id=run_id, session_id=state["session_id"])

    if result.get("status") == "unsolvable":
        reason = result.get("message", "No reason provided.")
        msg = f"Query cannot be answered with available tools: {reason}"
        log_event(logger, run_id, "replanner_failed", {"message": msg})
        return {"status": "unsolvable", "message": msg}

    if result.get("status") != "success":
        msg = f"Replanner failed: {result.get('message', 'Unknown error.')}"
        log_event(logger, run_id, "replanner_failed", {"message": msg})
        return {"status": "error", "message": msg}

    new_plan = result["plan"]
    log_event(logger, run_id, "replanner_completed", {
        "step_count": len(new_plan),
        "plan_summary": " -> ".join(s.tool for s in new_plan),
    })

    return {
        "plan": new_plan,
        "max_executions": len(new_plan) * 2,
        "current_step_index": 0,
        "retry_count": 0,
        "state_store": {"original_df": state["original_df"]},
        "status": "running",
        "message": "",
    }


# ---------------------------------------------------------------------------
# Answer Generator Node
# ---------------------------------------------------------------------------

def _fallback_answer(final_df: pd.DataFrame) -> str:
    """
    Deterministic, non-LLM answer built directly from the final result
    DataFrame. Used when generate_answer() fails — the DataFrame is always
    the source of truth.
    """
    if final_df.shape == (1, 1):
        col = final_df.columns[0]
        val = final_df.iloc[0, 0]
        return f"{col}: {val}"

    return f"Here is the result:\n{final_df.to_string(index=False)}"


def answer_gen_node(state: PipelineState) -> Dict[str, Any]:
    """
    Wraps generate_answer(). Reads `query` + `final_df` from state, writes
    `answer`.

    Graceful degradation: never touches `status`/`message`. If the LLM call
    fails, falls back to a deterministic answer built from `final_df`
    instead of returning None.
    """
    run_id = state["run_id"]
    final_df = state.get("final_df")

    if final_df is None or final_df.empty:
        return {"answer": None}

    logger = get_logger(run_id)
    result = generate_answer(state["query"], final_df, logger=logger, run_id=run_id, session_id=state["session_id"])

    if result["status"] == "success":
        return {"answer": result["answer"]}

    return {"answer": _fallback_answer(final_df)}
