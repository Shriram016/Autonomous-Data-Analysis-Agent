type Props = { steps: string[]; finished: boolean };

/** The live progress from the SSE stream: every step but the newest is done. */
export function Steps({ steps, finished }: Props) {
  if (steps.length === 0) return <p className="steps waiting">Waiting for a worker…</p>;
  return (
    <ol className="steps" aria-live="polite">
      {steps.map((step, index) => {
        const done = finished || index < steps.length - 1;
        return (
          <li key={step} className={done ? "done" : "active"}>
            <span className="mark" aria-hidden="true">
              {done ? "✓" : "…"}
            </span>
            {step}
          </li>
        );
      })}
    </ol>
  );
}
