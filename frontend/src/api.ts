// The only file in the page that talks to the backend (through Vite's /api proxy).
//
// The types come from the backend: src/api-types.ts is GENERATED from FastAPI's OpenAPI
// description, so the Pydantic models stay the one source of truth (§0 M1.6). After a
// backend change, regenerate:
//     backend/:   uv run python -m adaa.api.openapi
//     frontend/:  npm run types
// The SSE event shapes are not in OpenAPI, so they are typed by hand below.
import type { components } from "./api-types";

export type FinishedAnswer = components["schemas"]["FinishedAnswer"];
export type QuestionRecord = components["schemas"]["QuestionRecord"];
export type Chart = components["schemas"]["Chart"];
export type Table = components["schemas"]["Table"];

const API = "/api";
export const TOO_LONG = "Questions can be 1 to 500 characters.";

export class ApiError extends Error {}

export async function submitQuestion(question: string): Promise<string> {
  const reply = await fetch(`${API}/questions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (reply.status === 422) throw new ApiError(TOO_LONG);
  if (!reply.ok) throw new ApiError("The service could not take the question. Try again.");
  const body = (await reply.json()) as { id: string };
  return body.id;
}

export async function getQuestion(id: string): Promise<QuestionRecord> {
  const reply = await fetch(`${API}/questions/${id}`);
  if (reply.status === 404) throw new ApiError("No such question.");
  if (!reply.ok) throw new ApiError("The service could not load the question.");
  return (await reply.json()) as QuestionRecord;
}

// --- the live stream (SSE) ---

type StepData = { text: string };
type FinalData = { state: "done" | "failed"; answer: FinishedAnswer | null };

export type StreamHandlers = {
  onStep: (text: string) => void; // "Understanding the question…", "Running the query…"
  onDone: (answer: FinishedAnswer) => void; // the job ended: an answer OR a plain failure message
  onFailed: (message: string) => void; // the job itself crashed, or the stream gave up
};

// The part of the browser's EventSource we use; tests pass a fake instead.
export type EventSourceLike = {
  addEventListener: (name: string, listener: (event: MessageEvent<string>) => void) => void;
  close: () => void;
};
type MakeSource = (url: string) => EventSourceLike;
const browserSource: MakeSource = (url) => new EventSource(url);

/** Follow a question live. EventSource reconnects by itself and sends Last-Event-ID, so no
 *  reconnect code is needed here. Returns a function that stops following. */
export function followQuestion(
  id: string,
  handlers: StreamHandlers,
  makeSource: MakeSource = browserSource,
): () => void {
  const source = makeSource(`${API}/questions/${id}/events`);
  const finish = (data: string): FinalData => {
    source.close(); // the last event: stop, so the browser does not reconnect
    return JSON.parse(data) as FinalData;
  };

  source.addEventListener("step", (e) => handlers.onStep((JSON.parse(e.data) as StepData).text));
  source.addEventListener("done", (e) => {
    const { answer } = finish(e.data);
    if (answer) handlers.onDone(answer);
    else handlers.onFailed("The answer is missing. Reload the page.");
  });
  source.addEventListener("failed", (e) => {
    finish(e.data);
    handlers.onFailed("Something went wrong while answering. Please try again.");
  });
  source.addEventListener("timeout", (e) => {
    finish(e.data);
    handlers.onFailed("No answer yet. Reload the page to check again.");
  });
  return () => source.close();
}
