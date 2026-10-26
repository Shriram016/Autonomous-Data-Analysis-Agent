import type { FinishedAnswer } from "../api";
import { AnswerChart } from "./AnswerChart";

type Props = { answer: FinishedAnswer; onAsk: (question: string) => void };

/**
 * The answer: the sentence, the suggestion buttons (quick routes: clarify, refuse,
 * off-topic), the chart (when the result suits one), the table, and "How I got this".
 * A suggestion is a full question: a click asks it as a new question (no memory, §0 M2 2c).
 */
export function AnswerView({ answer, onAsk }: Props) {
  if (answer.status === "failed") {
    // The agent ran but could not answer (e.g. a place not in the data): a plain message.
    return <p className="message">{answer.text}</p>;
  }
  return (
    <section className="answer">
      <p className="answer-text">{answer.text}</p>

      {answer.suggestions.length > 0 && (
        <div className="suggestions">
          {answer.suggestions.map((question) => (
            <button
              key={question}
              type="button"
              className="suggestion"
              onClick={() => onAsk(question)}
            >
              {question}
            </button>
          ))}
        </div>
      )}

      {answer.chart && <AnswerChart chart={answer.chart} />}

      {answer.table && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {answer.table.headers.map((header) => (
                  <th key={header}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {answer.table.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td key={c}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {answer.how.length > 0 && (
        <details className="how">
          <summary>How I got this</summary>
          <ul>
            {answer.how.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
