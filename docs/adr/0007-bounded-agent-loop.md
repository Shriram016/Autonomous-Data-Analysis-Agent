# The agent works through a question in a bounded loop

The agent picks an allowed tool, sees the result, and picks the next step, with a hard step limit (e.g. max 5), only the tools allowed for the question, and a check after each step. Hybrid questions genuinely depend on earlier results ("find the worst categories, then search reviews for those"), and the approval step for actions fits naturally: the loop pauses, the manager confirms, the loop continues. The limits keep a free loop's flexibility without its unpredictability.

## Considered Options

- **Plan first (V1/V2).** LLM writes the whole plan, code runs it. Predictable and easy to test, but cannot adapt when one step's result changes the next. V2 used it by default, never by evidence. **Built as a comparison:** both run on the same questions, compared on accuracy, cost and speed.
- **Free loop.** Adapts, but may loop, wander or run up cost; hard to test. Rejected.

## Consequences

- Step limit, per-question time cap and allowed-tool list are enforced by code, not by the prompt.
- Checks after each step replace V2's after-the-fact critic as the main correction point.
- The approval pause needs durable state (the loop must resume after the manager confirms, possibly much later).
- Cost and latency vary more per question than plan-first; tracked against the speed and cost targets.

## Questions that drove this

- Do later steps depend on earlier results? (hybrid questions: yes)
- What stops the agent from looping forever or running up cost?
- Where does human approval fit in the flow?
- Was the old choice (plan-first) ever tested, or just assumed?
