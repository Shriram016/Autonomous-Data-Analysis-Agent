import { type FormEvent, useState } from "react";

const MAX_CHARS = 500; // the API's limit (§0)
const EXAMPLES = [
  "What was the total revenue?",
  "Revenue by customer state in 2017",
  "Late delivery rate by month",
];

type Props = { disabled: boolean; onAsk: (question: string) => void };

/** The text box, a character counter, the Ask button and three example questions. */
export function QuestionBox({ disabled, onAsk }: Props) {
  const [text, setText] = useState("");
  const question = text.trim();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (question && !disabled) onAsk(question);
  }

  return (
    <form className="question-box" onSubmit={submit}>
      <label htmlFor="question">Ask a question about the store's orders</label>
      <div className="question-row">
        <input
          id="question"
          type="text"
          value={text}
          maxLength={MAX_CHARS}
          placeholder="e.g. Revenue by customer state in 2017"
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
          autoComplete="off"
        />
        <button type="submit" disabled={disabled || !question}>
          Ask
        </button>
      </div>
      <div className="question-meta">
        <div className="examples">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="example"
              disabled={disabled}
              onClick={() => setText(example)}
            >
              {example}
            </button>
          ))}
        </div>
        <span className="counter">
          {text.length} / {MAX_CHARS}
        </span>
      </div>
    </form>
  );
}
