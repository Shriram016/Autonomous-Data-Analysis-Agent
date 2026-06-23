# Conversation-Style UI — TODO (V2 §7)

> **Context:** Read [docs/conversation-ui.md](conversation-ui.md) for the full design
> (per-turn render function, history ordering, dropping `current_result`, layout).

---

## Prerequisites

- [x] Review `docs/conversation-ui.md` design — confirm no open questions before coding

---

## Step 1: Extract `_render_turn(query, result)`

- [x] Add `_render_turn(query: str, result: dict) -> None` to `app.py`, wrapping today's
      result-rendering block (status banner, answer, result table, Execution Trace expander,
      Plan Steps expander) in `st.chat_message("user")` / `st.chat_message("assistant")`
- [x] Replace the `unsolvable` branch's `st.stop()` with a plain `return` from
      `_render_turn` — preserves "banner only, no Result/Trace/Plan" for that turn without
      aborting the rest of the loop
- [x] `success`/`error` branches keep rendering Answer / Result / Execution Trace / Plan
      Steps exactly as today (reuse `_trace_table`, `_plan_table`, `_df_height` unchanged)

---

## Step 2: History Order + Drop `current_result`

- [x] Change `st.session_state.history.insert(0, ...)` → `.append(...)` (chronological,
      oldest-first)
- [x] Remove `st.session_state.current_result` entirely (init + all reads/writes)
- [x] Sidebar "Session" expander: derive `recent_questions` from
      `st.session_state.history[-1]["result"].get("recent_questions", [])` if `history` is
      non-empty, else `[]`
- [x] `_confirm_new_session`: reset only `history` (now `[]`) and regenerate `session_id` —
      no `current_result` to clear

---

## Step 3: Scrollable Container + Chat Input

- [x] Replace the `st.form` + `st.text_input` + submit button block with:
  - `with st.container(height=550):` looping `st.session_state.history` oldest→newest,
    calling `_render_turn(item["query"], item["result"])`
  - `prompt = st.chat_input(...)` placed after the container
  - On `prompt`: `st.spinner(...)` → `run_pipeline(prompt, session_id=...)` → append to
    `history` → `st.rerun()`
- [x] Empty-state: when `history == []`, show a caption/placeholder (replaces today's
      `st.info("Enter a query above and press Run to get started.")`)

---

## Step 4: Sidebar Cleanup

- [x] Remove the "Query History" title + per-turn button list (the loop over
      `st.session_state.history` that sets `current_result`)
- [x] Keep "New Session" button + `_confirm_new_session` dialog, and the "Session" expander
      (session ID + recent questions, per Step 2)

---

## Step 5: Verify

- [x] Manual Streamlit run (`streamlit run app.py`):
  - Ask a query — appears as a user/assistant pair in the chat, container scrolls if needed
  - Ask a follow-up — both turns visible, oldest at top; sidebar "Session" shows both
    questions in `recent_questions`
  - Trigger an `unsolvable` query — banner-only turn, no Result/Trace/Plan, doesn't break
    rendering of turns before/after it
  - "New Session" button — clears the chat back to empty state, sidebar recent questions
    reset
  - Execution Trace / Plan Steps expanders collapse/expand correctly per turn
- [x] `python run_tests.py` — confirm no regression (this is a UI-only change; should be
      unaffected, but confirms `run_pipeline()` still called correctly)

---

## Files Changed

| Action | File |
|---|---|
| **Updated** | `app.py` |
| **Unchanged** | everything under `src/`, `eval/`, `dev_checks/` |
