"""
graph.py — V2 LangGraph wiring.

Replaces src/core/loop_controller.py. The nested for-loops (step
progression, retry, replan) become conditional edges that read counters
(`current_step_index`, `retry_count`, `total_executions`) from
PipelineState and route to the next node accordingly.

    schema_gen -> planner -> execute_step
                                  |
                    (conditional edge after execute_step)
                    +- success + more steps    -> execute_step (loop back)
                    +- success + last step     -> answer_gen
                    +- fail + retries left     -> param_fixer -> execute_step
                    +- fail + retries exhausted-> replanner
                    +- execution cap hit       -> END (error)

    replanner -> (conditional edge)
                    +- success -> execute_step (restart with new plan)
                    +- fail    -> END (error)

SQLite checkpointing (Step 7): build_graph() is a context manager that opens
a connection to CHECKPOINT_DB_PATH, compiles the graph with a SqliteSaver
bound to it, and closes the connection on exit. Callers must use it as
`with build_graph() as graph: ...` so invokes/streams happen while the
connection is open and persisted state is flushed and closed afterwards.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.core.state import PipelineState
from src.core.nodes import (
    schema_gen_node,
    planner_node,
    execute_step_node,
    param_fixer_node,
    replanner_node,
    answer_gen_node,
)
from src.config import MAX_RETRIES_PER_STEP, CHECKPOINT_DB_PATH


# ---------------------------------------------------------------------------
# Conditional Edge Functions
# ---------------------------------------------------------------------------

def _route_after_schema_gen(state: PipelineState) -> str:
    return END if state["status"] == "error" else "planner"


def _route_after_planner(state: PipelineState) -> str:
    if state["status"] in ("error", "unsolvable"):
        return END
    return "execute_step"


def _route_after_execute_step(state: PipelineState) -> str:
    if state["status"] == "error":
        if state["total_executions"] >= state["max_executions"]:
            return END
        if state["retry_count"] < MAX_RETRIES_PER_STEP:
            return "param_fixer"
        return "replanner"

    if state["current_step_index"] >= len(state["plan"]):
        return "answer_gen"
    return "execute_step"


def _route_after_replanner(state: PipelineState) -> str:
    if state["status"] in ("error", "unsolvable"):
        return END
    return "execute_step"


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------

@contextmanager
def build_graph(interrupt_after=None):
    """
    Builds and compiles the ADAA V2 graph with SQLite checkpointing.

    A context manager (not a plain function) because it owns a sqlite
    connection: the connection must stay open for the lifetime of any
    graph.invoke()/stream() call (so the checkpointer can read/write state)
    but should be closed afterwards. Usage:

        with build_graph() as graph:
            result = graph.invoke(state, config={"configurable": {"thread_id": run_id}})

    `interrupt_after` is forwarded to graph.compile() — e.g. pass
    ["execute_step"] to pause after that node (used by
    dev_checks/check_checkpointer.py to simulate a crash/resume).
    """
    Path(CHECKPOINT_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
    try:
        graph = StateGraph(PipelineState)

        graph.add_node("schema_gen", schema_gen_node)
        graph.add_node("planner", planner_node)
        graph.add_node("execute_step", execute_step_node)
        graph.add_node("param_fixer", param_fixer_node)
        graph.add_node("replanner", replanner_node)
        graph.add_node("answer_gen", answer_gen_node)

        graph.set_entry_point("schema_gen")

        graph.add_conditional_edges(
            "schema_gen", _route_after_schema_gen, {"planner": "planner", END: END}
        )
        graph.add_conditional_edges(
            "planner", _route_after_planner, {"execute_step": "execute_step", END: END}
        )
        graph.add_conditional_edges(
            "execute_step",
            _route_after_execute_step,
            {
                "execute_step": "execute_step",
                "param_fixer": "param_fixer",
                "replanner": "replanner",
                "answer_gen": "answer_gen",
                END: END,
            },
        )
        graph.add_edge("param_fixer", "execute_step")
        graph.add_conditional_edges(
            "replanner", _route_after_replanner, {"execute_step": "execute_step", END: END}
        )
        graph.add_edge("answer_gen", END)

        # pickle_fallback=True: state_store/original_df/final_df hold pandas
        # DataFrames, which the default msgpack serde can't encode.
        checkpointer = SqliteSaver(conn, serde=JsonPlusSerializer(pickle_fallback=True))
        yield graph.compile(checkpointer=checkpointer, interrupt_after=interrupt_after)
    finally:
        conn.close()
