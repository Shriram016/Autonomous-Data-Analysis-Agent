"""
Autonomous Data Analysis Agent — Streamlit UI
"""

import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.pipeline import run_pipeline


# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="ADAA — Data Analysis Agent",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------

if "history" not in st.session_state:
    st.session_state.history = []        # list of {"query": str, "result": dict}

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_query(query: str) -> None:
    """Runs the pipeline and appends the result to history."""
    with st.spinner("Running pipeline..."):
        result = run_pipeline(query, session_id=st.session_state.session_id)
    st.session_state.history.append({"query": query, "result": result})


def _trace_table(trace: list) -> pd.DataFrame:
    """Converts trace list to a display DataFrame."""
    rows = []
    for rec in trace:
        shape = rec.get("output_shape")
        rows.append({
            "Step":         rec.get("step", "?"),
            "Tool":         rec.get("tool", "?"),
            "Status":       "✅" if rec.get("status") == "success" else "❌",
            "Critic":       "✅" if rec.get("critic") == "pass" else "❌",
            "Output Shape": f"{shape[0]} × {shape[1]}" if shape else "—",
            "Message":      rec.get("message", ""),
        })
    return pd.DataFrame(rows)


def _plan_table(plan: list) -> pd.DataFrame:
    """Converts plan steps to a display DataFrame."""
    rows = []
    for step in plan:
        rows.append({
            "Step":       step.step,
            "Tool":       step.tool,
            "Parameters": str(step.parameters),
            "Input":      step.input,
            "Output":     step.output,
        })
    return pd.DataFrame(rows)


def _df_height(df: pd.DataFrame, row_height: int = 35, max_height: int = 400) -> int:
    """Returns a sensible fixed height for a scrollable dataframe."""
    return min(max_height, row_height * (len(df) + 1) + 10)


def _render_turn(query: str, result: dict) -> None:
    """Renders one user/assistant exchange — question and answer only."""
    with st.chat_message("user"):
        st.write(query)

    with st.chat_message("assistant"):
        status = result["status"]
        if status == "success":
            st.write(result.get("answer"))
        elif status == "unsolvable":
            st.warning(result.get("message", ""))
        else:
            st.error(result.get("message", ""))


def _render_details(result: dict) -> None:
    """Renders full details (banner, result table, trace, plan) for the latest turn."""
    status   = result["status"]
    run_id   = result["run_id"]
    final_df = result.get("final_df")
    trace    = result.get("trace", [])
    plan     = result.get("plan", [])
    total_ex = result.get("total_executions", 0)

    st.subheader("Latest Result")

    # ── Status banner ──────────────────────────────────────────────────────
    if status == "success":
        st.success(f"run `{run_id}` — {total_ex} execution(s) | {len(plan)} step(s)")
    elif status == "unsolvable":
        st.warning(f"Query cannot be answered with available tools: {result.get('message', '')}")
        return
    else:
        st.error(f"Pipeline error — {result.get('message', '')}")

    # ── Result Table ───────────────────────────────────────────────────────
    if final_df is not None:
        st.subheader("Result")
        st.dataframe(
            final_df,
            use_container_width=True,
            height=_df_height(final_df),
            hide_index=True,
        )

    # ── Execution Trace ────────────────────────────────────────────────────
    with st.expander("Execution Trace", expanded=False):
        if trace:
            trace_df = _trace_table(trace)
            st.dataframe(
                trace_df,
                use_container_width=True,
                height=_df_height(trace_df),
                hide_index=True,
            )
        else:
            st.caption("No trace available.")

    # ── Plan Steps ─────────────────────────────────────────────────────────
    with st.expander("Plan Steps", expanded=False):
        if plan:
            plan_df = _plan_table(plan)
            st.dataframe(
                plan_df,
                use_container_width=True,
                height=_df_height(plan_df),
                hide_index=True,
            )
        else:
            st.caption("No plan available.")


@st.dialog("Start a new session?")
def _confirm_new_session() -> None:
    st.write("This will clear the conversation history and start a fresh session.")
    col_yes, col_no = st.columns(2)
    if col_yes.button("Yes, start new session", type="primary", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.history = []
        st.toast("New session started")
        st.rerun()
    if col_no.button("Cancel", use_container_width=True):
        st.rerun()


# ---------------------------------------------------------------------------
# Sidebar — Session
# ---------------------------------------------------------------------------

with st.sidebar:
    if st.button("New Session", use_container_width=True):
        _confirm_new_session()

    if st.session_state.history:
        recent_questions = st.session_state.history[-1]["result"].get("recent_questions", [])
    else:
        recent_questions = []

    with st.expander("Session", expanded=False):
        st.caption(f"Session ID: `{st.session_state.session_id[:8]}`")
        if recent_questions:
            st.caption("Recent questions (context for follow-ups):")
            for q in recent_questions:
                st.caption(f"- {q}")
        else:
            st.caption("No recent questions yet.")


# ---------------------------------------------------------------------------
# Main — Header
# ---------------------------------------------------------------------------

st.title("Autonomous Data Analysis Agent")
st.caption(
    "Ask a question about the Sample Superstore dataset. "
    "The pipeline computes a verified answer — no free-form code generation."
)
st.divider()


# ---------------------------------------------------------------------------
# Main — Conversation
# ---------------------------------------------------------------------------

with st.container(height=550):
    if not st.session_state.history:
        st.caption("Ask a question to get started...")
    for item in st.session_state.history:
        _render_turn(item["query"], item["result"])

if st.session_state.history:
    _render_details(st.session_state.history[-1]["result"])

prompt = st.chat_input("Ask a question about the Sample Superstore dataset...")
if prompt:
    _run_query(prompt)
    st.rerun()

