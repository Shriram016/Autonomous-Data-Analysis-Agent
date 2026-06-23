# Conversation-Style UI — Design (V2 §7)

## What's Changing

Today `app.py` only renders `st.session_state.current_result` — a single turn. Every turn
is stored in `st.session_state.history` (newest-first), but the sidebar "Query History"
just lets you *swap* `current_result` to an old turn; you can't see the conversation as a
whole. With Session Memory (V2 §2) wired up — the planner already uses `recent_questions`
for follow-ups — the UI should look like an actual conversation: every turn visible,
oldest at the top, newest at the bottom, with a chat input pinned at the bottom.

**Scope boundary:** UI rendering only. No change to `run_pipeline()`, `PipelineState`,
session-memory plumbing, or any `src/core/*` module.

---

## Per-Turn Render Function

`_render_turn(query, result)` renders inside the scrollable chat container — **question and
answer only**. No run_id banner, no Result table, no Execution Trace/Plan Steps expanders.

```python
def _render_turn(query: str, result: dict) -> None:
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
```

## Latest Result Panel

`_render_details(result)` is called once outside the container, always on
`history[-1]["result"]` — the most recent turn. It renders the full detail view and
overwrites on each new query:

```python
def _render_details(result: dict) -> None:
    st.subheader("Latest Result")
    # status banner (st.success / st.warning / st.error with run_id + execution count)
    # for unsolvable: banner only, return early
    # for success/error: Result table + Execution Trace expander + Plan Steps expander
```

`_trace_table`, `_plan_table`, `_df_height` are reused as-is inside `_render_details`.

---

## History Order

`st.session_state.history` currently uses `.insert(0, ...)` (newest-first), used only by the
sidebar history-button list (being removed). Switch to `.append(...)` (oldest-first /
chronological) — matches how a chat reads top-to-bottom. Nothing else depends on the old
order.

---

## Dropping `current_result`

Since the chat container renders the full history including the latest turn,
`st.session_state.current_result` becomes redundant — `history[-1]` *is* "the latest
result". Remove the `current_result` session-state key entirely:

- `_run_query` (renamed/inlined into the chat_input handler) only appends to `history`.
- The sidebar's "Session" expander reads `recent_questions` from
  `history[-1]["result"].get("recent_questions", [])` if `history` is non-empty, else `[]`
  (replaces the `current_result.get("session_id") == st.session_state.session_id` check,
  which is no longer needed since `history` is always for the current `session_id`).
- `_confirm_new_session` no longer needs to reset `current_result` — just `history` and
  `session_id`.

---

## Layout: Scrollable Container + Chat Input

```python
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
```

- `st.container(height=550)` is fixed-height and internally scrollable — shows only
  question + answer per turn, so it stays compact even across many turns.
- `_render_details` sits between the container and `chat_input`, rendering full detail
  (banner, Result table, Execution Trace, Plan Steps) for the latest turn only. It
  overwrites on each new query since it always reads `history[-1]`.
- `st.chat_input(...)` is docked to the bottom of the app automatically by Streamlit.
- When `history` is empty, the container shows a caption placeholder; `_render_details`
  is skipped.

---

## Sidebar Changes

- **Keep**: "New Session" button + confirmation dialog (`_confirm_new_session`), "Session"
  expander (session ID + recent questions).
- **Remove**: "Query History" title + the per-turn button list (lines ~128-147 of
  `app.py`) — redundant now that every turn is visible in the chat.

---

## Files That Will Change

| File | Change |
|---|---|
| `app.py` | Replace form+single-result rendering with chat_message/chat_input + scrollable history container + `_render_turn()`; drop `current_result`; switch `history` to append-order; remove sidebar Query History list |

**Unchanged:** everything under `src/`, `eval/`, `dev_checks/` — this is a pure `app.py`
rendering change.
