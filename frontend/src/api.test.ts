import { afterEach, describe, expect, it, vi } from "vitest";

import {
  type EventSourceLike,
  type FinishedAnswer,
  followQuestion,
  submitQuestion,
  TOO_LONG,
} from "./api";

afterEach(() => vi.unstubAllGlobals());

function replyWith(status: number, body: unknown = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

describe("submitQuestion", () => {
  it("returns the id", async () => {
    replyWith(202, { id: "7f3a" });
    await expect(submitQuestion("Total revenue")).resolves.toBe("7f3a");
  });

  it("turns a 422 into the plain length message", async () => {
    replyWith(422, { detail: [] });
    await expect(submitQuestion("x".repeat(501))).rejects.toThrow(TOO_LONG);
  });
});

/** A stand-in for the browser's EventSource that a test can push events into. */
class FakeSource implements EventSourceLike {
  url = "";
  closed = false;
  listeners = new Map<string, (event: MessageEvent<string>) => void>();
  addEventListener(name: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.set(name, listener);
  }
  close() {
    this.closed = true;
  }
  emit(name: string, data: unknown) {
    this.listeners.get(name)?.(new MessageEvent(name, { data: JSON.stringify(data) }));
  }
}

const ANSWER = { status: "answered", text: "Revenue was R$ 100.00." } as FinishedAnswer;

describe("followQuestion", () => {
  it("passes each step on, then the answer, then stops", () => {
    const source = new FakeSource();
    const steps: string[] = [];
    let done: FinishedAnswer | undefined;
    followQuestion(
      "7f3a",
      { onStep: (t) => steps.push(t), onDone: (a) => (done = a), onFailed: () => {} },
      (url) => {
        source.url = url;
        return source;
      },
    );
    source.emit("step", { text: "Understanding the question…" });
    source.emit("step", { text: "Running the query…" });
    source.emit("done", { state: "done", answer: ANSWER });

    expect(source.url).toBe("/api/questions/7f3a/events");
    expect(steps).toEqual(["Understanding the question…", "Running the query…"]);
    expect(done?.text).toBe("Revenue was R$ 100.00.");
    expect(source.closed).toBe(true); // no reconnect after the last event
  });

  it("reports a crashed job as a plain message", () => {
    const source = new FakeSource();
    let message = "";
    followQuestion(
      "7f3a",
      { onStep: () => {}, onDone: () => {}, onFailed: (m) => (message = m) },
      () => source,
    );
    source.emit("failed", { state: "failed", answer: null });
    expect(message).toContain("Something went wrong");
    expect(source.closed).toBe(true);
  });
});
