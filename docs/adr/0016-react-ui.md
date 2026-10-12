# The UI is a thin React single-page app (Vite, TypeScript) calling the backend

The manager-facing UI is a React single-page app built with Vite and TypeScript, using a ready-made component library. It is a thin client: login screens, per-manager conversation screens, streamed progress, answers with "how it was computed", review citations, clarify flow, approval buttons for actions, and 👍/👎 feedback; all logic stays in the backend. React is what real products use, and per-user screens and proper login are easier there than in Streamlit.

## Considered Options

- **Streamlit (V2).** Low effort and familiar, but reruns the whole script per interaction, gets clunky for multi-screen apps with login, and reads as a prototype. Rejected.
- **Chainlit.** Built for LLM chat apps, but the original team stepped back in 2025 and it is community-maintained: risky for a long-lived portfolio piece. Rejected.
- **Gradio.** Reads as an ML demo; weak for multi-step chat apps. Rejected.
- **Next.js.** Adds its own server layer, which the FastAPI backend already provides. Rejected in favour of plain React + Vite.

## Consequences

- New language and ecosystem for the builder; mitigated by keeping the UI thin and using a component library. Interview line: "the UI is a thin client; my focus was the agent and backend".
- Because the UI is only an API client, it can be replaced without touching the backend.
- Login is implemented in the backend (token-based); the UI only stores and sends the token.
- One more service to build, test and deploy.

## Questions that drove this

- Where is the project's value judged: the UI or the agent/backend?
- What do real products use, and does the UI need per-user screens and login?
- How much of the UI code must the builder be able to explain?
- Does the frontend framework duplicate something the backend already does?
