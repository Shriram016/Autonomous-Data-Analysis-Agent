"""
PipelineState — the single shared typed state object passed through every
node in the V2 LangGraph pipeline.

Replaces the scattered dicts and function arguments used in V1
(see docs/langgraph-migration.md for the full design discussion).
"""

from typing import TypedDict, Optional

import pandas as pd

from src.core.planner import PlanStep


class PipelineState(TypedDict):
    # -----------------------------------------------------------------
    # Inputs (set once at graph entry)
    # -----------------------------------------------------------------
    query: str
    run_id: str
    original_df: pd.DataFrame
    recent_questions: list[str]

    # -----------------------------------------------------------------
    # Schema Gen output
    # -----------------------------------------------------------------
    schema: Optional[dict]

    # -----------------------------------------------------------------
    # Planner output
    # -----------------------------------------------------------------
    plan: list[PlanStep]
    max_executions: int

    # -----------------------------------------------------------------
    # Execution state
    # -----------------------------------------------------------------
    state_store: dict[str, pd.DataFrame]
    current_step_index: int
    retry_count: int
    total_executions: int
    trace: list[dict]

    # -----------------------------------------------------------------
    # Final outputs
    # -----------------------------------------------------------------
    final_df: Optional[pd.DataFrame]
    status: str
    message: str
    answer: Optional[str]
