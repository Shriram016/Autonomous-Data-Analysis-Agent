# Guardrails are one separate layer, checking before, during and after

Checks outside the LLM catch wrong or attacked behaviour before the manager sees it, at three points:

| Point | Checks |
|---|---|
| **Before (input)** | Off-topic and personal-data requests; prompt-injection detection on the question |
| **During (before running)** | Structured request validated against the semantic layer (real metric/dimension, valid dates); review text wrapped and marked as untrusted data, never instructions |
| **After (output)** | Every number in the answer must appear in the query result; every quote must match a retrieved review; personal data masked. A failing answer is blocked or retried, never shown |

Built as one module with its own tests, not checks scattered through the code. Deterministic code first (exact number matching, validation); an LLM judge only where code can't decide, keeping checks fast and cheap. The after-check directly protects "never silently wrong" for a manager who cannot verify answers.

## Considered Options

- **Rely on prompts ("only use numbers from the result").** Prompts are requests, not guarantees. Rejected.
- **Output checks only.** Misses injection and invalid requests until after the expensive work. Rejected.
- **LLM judge for every check.** Slower, costs money, and is itself fallible where exact code works. Rejected as the default.

## Consequences

- Blocked answers count as a failure cause in the eval (which guardrail fired, and was it right).
- Retries after a blocked answer consume steps from the bounded loop's limit.
- Guardrail false positives (blocking a correct answer) must be measured too.
- A written prompt-injection threat model accompanies this layer.

## Questions that drove this

- Where can a wrong or malicious answer enter: the question, the review text, or the LLM's output?
- Which checks can code do exactly, and which need judgment?
- What happens when a check fails: block, retry, or warn?
