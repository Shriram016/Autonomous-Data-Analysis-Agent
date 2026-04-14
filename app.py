"""
Autonomous Data Analysis Agent — Streamlit UI
"""

import sys
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

if "current_result" not in st.session_state:
    st.session_state.current_result = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_query(query: str) -> None:
    """Runs the pipeline, stores result in session state and history."""
    with st.spinner("Running pipeline..."):
        result = run_pipeline(query)
    st.session_state.current_result = result
    st.session_state.history.insert(0, {"query": query, "result": result})


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


# ---------------------------------------------------------------------------
# Sidebar — Query History
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Query History")

    if not st.session_state.history:
        st.caption("No queries yet this session.")
    else:
        for i, item in enumerate(st.session_state.history):
            label = item["query"]
            short = label[:55] + "..." if len(label) > 55 else label
            status_icon = (
                "✅" if item["result"]["status"] == "success"
                else "⚠️" if item["result"]["status"] == "unsolvable"
                else "❌"
            )
            if st.button(
                f"{status_icon} {short}",
                key=f"hist_{i}",
                use_container_width=True,
            ):
                st.session_state.current_result = item["result"]


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
# Main — Query Input
# ---------------------------------------------------------------------------

with st.form("query_form", clear_on_submit=False):
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        query = st.text_input(
            label="query",
            placeholder="e.g. Who are the top 10 customers by sales in the last 3 months?",
            label_visibility="collapsed",
        )
    with col_btn:
        submitted = st.form_submit_button("Run", type="primary", use_container_width=True)

if submitted and query.strip():
    _run_query(query.strip())


# ---------------------------------------------------------------------------
# Main — Results
# ---------------------------------------------------------------------------

result = st.session_state.current_result

if result is None:
    st.info("Enter a query above and press Run to get started.")
    st.stop()

status  = result["status"]
run_id  = result["run_id"]
final_df = result.get("final_df")
answer   = result.get("answer")
trace    = result.get("trace", [])
plan     = result.get("plan", [])
total_ex = result.get("total_executions", 0)

# ── Status banner ──────────────────────────────────────────────────────────
if status == "success":
    st.success(f"run `{run_id}` — {total_ex} execution(s) | {len(plan)} step(s)")
elif status == "unsolvable":
    st.warning(f"Query cannot be answered with available tools: {result.get('message', '')}")
    st.stop()
else:
    st.error(f"Pipeline error — {result.get('message', '')}")

# ── Answer ─────────────────────────────────────────────────────────────────
if answer:
    st.subheader("Answer")
    st.info(answer)

# ── Result Table ───────────────────────────────────────────────────────────
if final_df is not None:
    st.subheader("Result")
    st.dataframe(
        final_df,
        use_container_width=True,
        height=_df_height(final_df),
        hide_index=True,
    )

# ── Execution Trace ────────────────────────────────────────────────────────
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

# ── Plan Steps ─────────────────────────────────────────────────────────────
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

