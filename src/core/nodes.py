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
from src.core.answer_generator import generate_answer
from src.utils.data_loader import DATE_COLUMNS
from src.utils.logger import get_logger, log_event


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

    On error/unsolvable, sets `status` + `message`, and `plan=[]`,
    `max_executions=0` so downstream conditional edges (Step 4) can route
    to END.
    """
    run_id = state["run_id"]
    logger = get_logger(run_id)
    query = state["query"]
    schema = state["schema"]

    log_event(logger, run_id, "planner_started", {"query": query})

    result = plan(query, schema, logger=logger, run_id=run_id)

    if result["status"] == "error":
        msg = f"Planner failed: {result['message']}"
        log_event(logger, run_id, "planner_failed", {"message": msg})
        return {"status": "error", "message": msg, "plan": [], "max_executions": 0}

    if result["status"] == "unsolvable":
        reason = result["reason"]
        log_event(logger, run_id, "planner_unsolvable", {"reason": reason})
        return {
            "status": "unsolvable",
            "message": f"Query cannot be answered with available tools: {reason}",
            "plan": [],
            "max_executions": 0,
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

    return {"plan": plan_steps, "max_executions": max_executions}


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
    result = generate_answer(state["query"], final_df, logger=logger, run_id=run_id)

    if result["status"] == "success":
        return {"answer": result["answer"]}

    return {"answer": _fallback_answer(final_df)}
