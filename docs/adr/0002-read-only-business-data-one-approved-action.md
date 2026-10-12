# Business data is read-only; one approved write action into agent-owned tables

The agent never changes business data (orders, reviews, sellers). It has one write action, flagging a seller or creating a task, saved only in its own separate tables. Every write needs the manager's approval first, is logged, and can be undone. Every locked question type only needs reading, and the pain we solve is "a trusted answer in seconds", not "do things for me". But the write-safety pattern (approval, audit, no double execution, undo) is what interviewers look for, so we show it where it cannot damage source data.

## Considered Options

- **Fully read-only.** Matches real analytics agents (Snowflake Cortex Analyst, Databricks Genie, ThoughtSpot). Rejected as the whole answer because it leaves no place to show human approval and safe side effects.
- **Agent edits business data** (orders, refunds). Rejected: a real company would not grant an analytics agent this; one bad write corrupts the numbers every answer depends on; a Kaggle snapshot has no real system behind it.
- **Report export / scheduled email.** Moved to later: side effect without touching data, but the seller-flag/task action shows the write path more fully.

## Consequences

- Two kinds of database access: a read-only role for business data; a separate, narrow write permission for the agent's own tables only.
- The approval step needs a design (where the agent pauses, how the manager confirms) — part of the agent-loop decision.
- Writes must be safe to retry (no duplicate flags) and reversible.

## Questions that drove this

- Do any of the question types actually need writing?
- What access would a real company give this agent? (least privilege)
- If a write goes wrong, what breaks, and can it be undone?
- What does a reviewer want to see from writes: the write itself, or the safety around it?
