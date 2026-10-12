# One agent (router + bounded loop), not a multi-agent system

The system uses a single agent: the router picks a route, and one bounded loop works with only that route's tools. This already delivers the main benefit of specialist agents (a focused prompt and toolset) without agent-to-agent hand-offs.

## Why not multi-agent (supervisor + specialist SQL / review agents)

1. **Specialisation is already there.** Route-specific toolsets give each run a focused prompt.
2. **Speed and cost targets.** Numbers under 5s and under $0.01 per question leave little room for extra hand-off calls.
3. **Trust.** Every hand-off is another place an error can hide or be passed on, and the manager cannot verify answers.
4. **Testability and tracing.** One loop is far easier to test, trace and attribute failures to a component.

## Revisit trigger

The task grows much broader (many data domains, long open-ended research tasks), or evals show one loop failing because its context or toolset is too large. Then specialists may earn their cost; re-plan at that point.

## Questions that drove this

- What would multiple agents give us that the router + route-specific tools don't already?
- How many extra LLM calls would hand-offs add, against the speed and cost targets?
- Where can errors hide, and can we still trace each failure to one component?
