// The page: ask a question, watch the steps arrive live, read the answer.
//
// The question id is kept in the address (?q=<id>), so a page reload fetches the answer
// again instead of losing it.
import { useEffect, useRef, useState } from "react";

import { ApiError, type FinishedAnswer, followQuestion, getQuestion, submitQuestion } from "./api";
import { AnswerView } from "./components/AnswerView";
import { QuestionBox } from "./components/QuestionBox";
import { Steps } from "./components/Steps";

type Phase =
  | { kind: "idle" }
  | { kind: "asking"; steps: string[] }
  | { kind: "answered"; steps: string[]; answer: FinishedAnswer }
  | { kind: "error"; message: string };

const SERVICE_DOWN = "The service is not answering. Check that the API is running.";

function setQuestionInAddress(id: string | null) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("q", id);
  else url.searchParams.delete("q");
  window.history.replaceState(null, "", url);
}

export function App() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const stopStream = useRef<(() => void) | null>(null);

  function follow(id: string) {
    stopStream.current?.();
    setPhase({ kind: "asking", steps: [] });
    stopStream.current = followQuestion(id, {
      onStep: (text) =>
        setPhase((p) => (p.kind === "asking" ? { ...p, steps: [...p.steps, text] } : p)),
      onDone: (answer) =>
        setPhase((p) => ({ kind: "answered", steps: p.kind === "asking" ? p.steps : [], answer })),
      onFailed: (message) => setPhase({ kind: "error", message }),
    });
  }

  async function ask(question: string) {
    try {
      const id = await submitQuestion(question);
      setQuestionInAddress(id);
      follow(id);
    } catch (error) {
      setPhase({ kind: "error", message: error instanceof ApiError ? error.message : SERVICE_DOWN });
    }
  }

  // After a reload: pick the question up from the address.
  useEffect(() => {
    const id = new URL(window.location.href).searchParams.get("q");
    if (!id) return;
    getQuestion(id)
      .then((record) => {
        if (record.state === "done" && record.answer) {
          setPhase({ kind: "answered", steps: [], answer: record.answer });
        } else if (record.state === "failed") {
          setPhase({ kind: "error", message: "Something went wrong while answering. Please try again." });
        } else {
          follow(id); // still waiting or running: watch it live
        }
      })
      .catch(() => setQuestionInAddress(null)); // unknown or old id: start fresh
    return () => stopStream.current?.();
  }, []);

  const busy = phase.kind === "asking";
  return (
    <main className="page">
      <header>
        <h1>ADAA</h1>
        <p className="subtitle">Answers from Olist's Brazilian e-commerce data, 2016–2018</p>
      </header>

      <QuestionBox disabled={busy} onAsk={ask} />

      {(phase.kind === "asking" || (phase.kind === "answered" && phase.steps.length > 0)) && (
        <Steps steps={phase.steps} finished={phase.kind === "answered"} />
      )}
      {phase.kind === "answered" && <AnswerView answer={phase.answer} />}
      {phase.kind === "error" && <p className="message">{phase.message}</p>}
    </main>
  );
}
