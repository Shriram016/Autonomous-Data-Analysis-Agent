# Long-term memory stores only preferences the manager explicitly asks to save

Across conversations, the agent remembers only what the manager explicitly asks it to ("remember that I manage São Paulo", "revenue for me includes freight"). Preferences are stored per manager in agent-owned tables, viewable and deletable. Any preference used in an answer is stated in that answer's explanation ("Using your saved preference: revenue includes freight"). A wrong or outdated memory would silently change answers for a manager who cannot verify them, so nothing is remembered without the manager knowing.

## Considered Options

- **No long-term memory.** Simple, but the manager repeats context in every chat. Rejected.
- **Automatic memory** (agent decides what to remember). Feels smart, but may store wrong things that then silently change answers; conflicts with trust. Rejected.

## Consequences

- Saved preferences live in agent-owned tables (consistent with ADR 0002); saving is the manager's own explicit request, so no separate approval step.
- Preferences that change a metric's meaning must map onto semantic-layer definitions, not free text.
- Eval needs cases where a saved preference must (and must not) change the answer.
- Gap noted: long-term memory was missing from the original reference checklist; found by the builder's question.

## Questions that drove this

- What happens if a memory is wrong or outdated, and would anyone notice?
- Who decides what gets remembered: the manager or the agent?
- How does the manager see, change or delete what is remembered?
