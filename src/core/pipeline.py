import logging
import uuid
from typing import Any, Dict, List, Optional

import pandas as pd

from src.utils.data_loader import load_dataset
from src.utils.logger import get_logger, log_event
from src.core.planner import PlanStep
from src.core.graph import build_graph
from src.config import GRAPH_RECURSION_LIMIT
from src.utils.langfuse_helper import graph_trace
# from src.core.schema_gen import generate_schema
# from src.core.planner import plan
# from src.core.loop_controller import run
# from src.core.answer_generator import generate_answer


# ---------------------------------------------------------------------------
# Response Builder
# ---------------------------------------------------------------------------

def _make_response(
    run_id: str,
    status: str,
    query: str,
    schema: Optional[Dict],
    plan_steps: Optional[List[PlanStep]],
    final_df: Optional[pd.DataFrame],
    message: str,
    trace: List,
    total_executions: int,
    answer: Optional[str] = None,
    session_id: Optional[str] = None,
    recent_questions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "run_id":            run_id,
        "status":            status,
        "query":             query,
        "schema":            schema,
        "plan":              plan_steps,
        "final_df":          final_df,
        "message":           message,
        "trace":             trace,
        "total_executions":  total_executions,
        "answer":            answer,
        "session_id":        session_id,
        "recent_questions":  recent_questions if recent_questions is not None else [],
    }


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def run_pipeline(query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes the full ADAA pipeline for a natural language query.

    Stages:
        1. Load dataset from fixed path (data/Sample - Superstore.csv)
        2. Run the V2 LangGraph (schema_gen -> planner -> execute_step loop
           -> answer_gen), which replaces the old schema_gen/planner/
           loop_controller calls below.

    Args:
        query      : Natural language query from the user.
        session_id : Caller-supplied session identifier, used as the
                      LangGraph `thread_id` to carry `recent_questions`
                      across calls (V2 session memory). If omitted, a fresh
                      UUID is generated — the run has no prior checkpoint,
                      so `recent_questions` starts empty. Pass the same
                      `session_id` on the next call to continue the session.

    Returns:
        {
            "run_id":           str,
            "status":           "success" | "error" | "unsolvable",
            "query":            str,
            "schema":           dict | None,
            "plan":             List[PlanStep] | None,
            "final_df":         pd.DataFrame | None,
            "message":          str,
            "trace":            list of per-step trace records,
            "total_executions": int,
            "session_id":       str,
            "recent_questions": list[str]
        }
    """
    run_id = str(uuid.uuid4())[:8]
    session_id = session_id or str(uuid.uuid4())
    logger = get_logger(run_id)

    try:
        log_event(logger, run_id, "query_received", {"query": query, "session_id": session_id})

        # ------------------------------------------------------------------
        # Stage 1 — Load Dataset
        # ------------------------------------------------------------------
        log_event(logger, run_id, "data_loader_started", {"path": "data/Sample - Superstore.csv"})
        try:
            df = load_dataset()
        except Exception as e:
            msg = f"Failed to load dataset: {str(e)}"
            log_event(logger, run_id, "data_loader_failed", {"message": msg})
            return _make_response(run_id, "error", query, None, None, None, msg, [], 0, session_id=session_id)

        log_event(logger, run_id, "data_loader_completed", {
            "rows": len(df),
            "cols": len(df.columns),
        })

        # ------------------------------------------------------------------
        # Stage 2 — Schema Gen / Planner / Execute / Answer (LangGraph)
        # ------------------------------------------------------------------
        # The graph (src/core/graph.py) wires together schema_gen_node,
        # planner_node, execute_step_node (looped via conditional edges,
        # with param_fixer/replanner on failure), and answer_gen_node.
        # Each node logs its own start/complete/failed events (see
        # src/core/nodes.py), so per-stage logging is no longer duplicated
        # here.
        config = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": GRAPH_RECURSION_LIMIT,
        }

        with build_graph() as graph:
            # Retrieve recent_questions from this session's last checkpoint
            # (V2 session memory) — empty if this is the first query on
            # this session_id.
            prior_state = graph.get_state(config)
            recent_questions = (prior_state.values or {}).get("recent_questions", [])

            initial_state = {
                "query": query,
                "run_id": run_id,
                "session_id": session_id,
                "original_df": df,
                "recent_questions": recent_questions,
                "schema": None,
                "plan": [],
                "max_executions": 0,
                "state_store": {"original_df": df},
                "current_step_index": 0,
                "retry_count": 0,
                "total_executions": 0,
                "trace": [],
                "final_df": None,
                "status": "pending",
                "message": "",
                "answer": None,
            }

            with graph_trace(run_id, session_id) as callbacks:
                config["callbacks"] = callbacks
                final_state = graph.invoke(initial_state, config=config)

        # The graph ends with status="running" on a clean success (no node
        # sets status="success" explicitly) — map that to "success" for
        # callers. "error" and "unsolvable" pass through unchanged.
        status = "success" if final_state["status"] == "running" else final_state["status"]

        # ------------------------------------------------------------------
        # Final outcome
        # ------------------------------------------------------------------
        final_event = "pipeline_complete" if status == "success" else "pipeline_error"
        log_event(logger, run_id, final_event, {
            "status":            status,
            "message":           final_state.get("message", ""),
            "total_executions":  final_state.get("total_executions", 0),
            "steps_in_plan":     len(final_state.get("plan", [])),
        })

        # Log final result — shape + preview (success only)
        final_df = final_state.get("final_df")
        if status == "success" and final_df is not None:
            log_event(logger, run_id, "final_result", {
                "shape":   tuple(final_df.shape),
                "columns": list(final_df.columns),
                "preview": final_df.head(10).to_dict(orient="records"),
            })

        return _make_response(
            run_id,
            status,
            query,
            final_state.get("schema"),
            final_state.get("plan"),
            final_df,
            final_state.get("message", ""),
            final_state.get("trace", []),
            final_state.get("total_executions", 0),
            answer=final_state.get("answer"),
            session_id=session_id,
            recent_questions=final_state.get("recent_questions", []),
        )

    except Exception as e:
        msg = f"Unexpected pipeline crash: {type(e).__name__}: {str(e)}"
        log_event(logger, run_id, "pipeline_crash", {"message": msg}, level=logging.ERROR)
        return _make_response(run_id, "error", query, None, None, None, msg, [], 0, session_id=session_id)
