import logging
import uuid
from typing import Any, Dict, List, Optional

import pandas as pd

from src.utils.data_loader import load_dataset, DATE_COLUMNS
from src.utils.logger import get_logger, log_event
from src.core.schema_gen import generate_schema
from src.core.planner import plan, PlanStep
from src.core.loop_controller import run
from src.core.answer_generator import generate_answer


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
    }


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def run_pipeline(query: str) -> Dict[str, Any]:
    """
    Executes the full ADAA pipeline for a natural language query.

    Stages:
        1. Load dataset from fixed path (data/Sample - Superstore.csv)
        2. Generate schema (passed to Planner — raw df never sent to LLM)
        3. Plan (LLM converts query + schema → structured JSON plan)
        4. Execute (Loop Controller runs plan with retry/replan logic)

    Args:
        query : Natural language query from the user.

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
            "total_executions": int
        }
    """
    run_id = str(uuid.uuid4())[:8]
    logger = get_logger(run_id)

    try:
        log_event(logger, run_id, "query_received", {"query": query})

        # ------------------------------------------------------------------
        # Stage 1 — Load Dataset
        # ------------------------------------------------------------------
        log_event(logger, run_id, "data_loader_started", {"path": "data/Sample - Superstore.csv"})
        try:
            df = load_dataset()
        except Exception as e:
            msg = f"Failed to load dataset: {str(e)}"
            log_event(logger, run_id, "data_loader_failed", {"message": msg})
            return _make_response(run_id, "error", query, None, None, None, msg, [], 0)

        log_event(logger, run_id, "data_loader_completed", {
            "rows": len(df),
            "cols": len(df.columns),
        })

        # ------------------------------------------------------------------
        # Stage 2 — Schema Generator
        # ------------------------------------------------------------------
        log_event(logger, run_id, "schema_gen_started", {"rows": len(df), "cols": len(df.columns)})

        schema_result = generate_schema(df, required_date_columns=DATE_COLUMNS)

        if schema_result["status"] == "error":
            msg = f"Schema generation failed: {schema_result['message']}"
            log_event(logger, run_id, "schema_gen_failed", {"message": msg})
            return _make_response(run_id, "error", query, None, None, None, msg, [], 0)

        schema = schema_result["result"]
        log_event(logger, run_id, "schema_gen_completed", {
            "column_count": len(schema),
            "columns": list(schema.keys()),
        })

        # ------------------------------------------------------------------
        # Stage 3 — Planner
        # ------------------------------------------------------------------
        log_event(logger, run_id, "planner_started", {"query": query})

        plan_result = plan(query, schema, logger=logger, run_id=run_id)

        if plan_result["status"] == "error":
            msg = f"Planner failed: {plan_result['message']}"
            log_event(logger, run_id, "planner_failed", {"message": msg})
            return _make_response(run_id, "error", query, schema, None, None, msg, [], 0)

        if plan_result["status"] == "unsolvable":
            reason = plan_result["reason"]
            log_event(logger, run_id, "planner_unsolvable", {"reason": reason})
            return _make_response(
                run_id, "unsolvable", query, schema, None, None,
                f"Query cannot be answered with available tools: {reason}", [], 0
            )

        plan_steps = plan_result.get("plan", [])
        log_event(logger, run_id, "planner_completed", {
            "step_count": len(plan_steps),
            "plan_summary": " -> ".join(s.tool for s in plan_steps),
            "steps": [
                {"step": s.step, "tool": s.tool, "parameters": s.parameters}
                for s in plan_steps
            ],
        })

        # ------------------------------------------------------------------
        # Stage 4 — Loop Controller
        # ------------------------------------------------------------------
        log_event(logger, run_id, "loop_controller_started", {
            "step_count":    len(plan_steps),
            "plan_summary":  " -> ".join(s.tool for s in plan_steps),
            "max_executions": len(plan_steps) * 2,
        })

        exec_result = run(plan_result, df, query, schema, logger=logger, run_id=run_id)

        # Log each step from trace individually
        for record in exec_result.get("trace", []):
            step_status = record.get("status", "")
            log_event(
                logger, run_id, "step_executed",
                {
                    "step":         record.get("step"),
                    "tool":         record.get("tool"),
                    "status":       step_status,
                    "message":      record.get("message"),
                    "output_shape": record.get("output_shape"),
                    "critic":       record.get("critic"),
                },
                level=logging.WARNING if step_status == "error" else logging.INFO,
            )

        if exec_result["status"] == "success":
            log_event(logger, run_id, "loop_controller_completed", {
                "status":           "success",
                "total_executions": exec_result.get("total_executions", 0),
                "steps_in_plan":    len(plan_steps),
            })
        else:
            log_event(logger, run_id, "loop_controller_failed", {
                "status":           "error",
                "message":          exec_result.get("message", ""),
                "total_executions": exec_result.get("total_executions", 0),
            }, level=logging.WARNING)

        # ------------------------------------------------------------------
        # Final outcome
        # ------------------------------------------------------------------
        final_event = "pipeline_complete" if exec_result["status"] == "success" else "pipeline_error"
        log_event(logger, run_id, final_event, {
            "status":            exec_result["status"],
            "message":           exec_result.get("message", ""),
            "total_executions":  exec_result.get("total_executions", 0),
            "steps_in_plan":     len(plan_steps),
        })

        # Log final result — shape + preview (success only)
        final_df = exec_result.get("final_df")
        if exec_result["status"] == "success" and final_df is not None:
            log_event(logger, run_id, "final_result", {
                "shape":   tuple(final_df.shape),
                "columns": list(final_df.columns),
                "preview": final_df.head(10).to_dict(orient="records"),
            })

        # ------------------------------------------------------------------
        # Stage 5 — Answer Generator (success only, graceful degradation)
        # ------------------------------------------------------------------
        answer = None
        if exec_result["status"] == "success" and final_df is not None:
            answer_result = generate_answer(query, final_df, logger=logger, run_id=run_id)
            if answer_result["status"] == "success":
                answer = answer_result["answer"]

        return _make_response(
            run_id,
            exec_result["status"],
            query,
            schema,
            plan_result.get("plan"),
            exec_result.get("final_df"),
            exec_result.get("message", ""),
            exec_result.get("trace", []),
            exec_result.get("total_executions", 0),
            answer=answer,
        )

    except Exception as e:
        msg = f"Unexpected pipeline crash: {type(e).__name__}: {str(e)}"
        log_event(logger, run_id, "pipeline_crash", {"message": msg}, level=logging.ERROR)
        return _make_response(run_id, "error", query, None, None, None, msg, [], 0)
