import { type ReactElement, type ReactNode, isValidElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { FinishedAnswer } from "../api";
import { AnswerView } from "./AnswerView";

const BASE: FinishedAnswer = {
  question: "What are our best products?",
  status: "answered",
  text: "Best by what? Pick one:",
  suggestions: [],
  how: [],
  used_template: false,
  versions: { semantic_layer: "0.4.0 (x)", agent_prompt: "0.2.0 (y)", answer_prompt: "0.2.0 (z)" },
  usage: { input_tokens: 0, output_tokens: 0, thinking_tokens: 0, cost_usd: 0 },
};
const CLARIFY: FinishedAnswer = {
  ...BASE,
  route: "clarify",
  suggestions: ["Top 5 product categories by revenue", "Top 5 product categories by items sold"],
};

/** Every element in a rendered tree (no DOM needed: the tests run in Node). */
function elements(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<{ children?: ReactNode }>(node)) return [];
  return [node as ReactElement<Record<string, unknown>>, ...elements(node.props.children)];
}

describe("AnswerView suggestions", () => {
  it("shows one button per suggestion", () => {
    const html = renderToStaticMarkup(<AnswerView answer={CLARIFY} onAsk={() => {}} />);
    expect(html.match(/class="suggestion"/g)).toHaveLength(2);
    expect(html).toContain("Top 5 product categories by revenue");
    expect(html).not.toContain("How I got this"); // a quick reply has no method lines
  });

  it("asks the clicked suggestion as a new question", () => {
    const asked: string[] = [];
    const tree = AnswerView({ answer: CLARIFY, onAsk: (q) => asked.push(q) });
    const buttons = elements(tree).filter((e) => e.props.className === "suggestion");
    (buttons[1].props.onClick as () => void)();
    expect(asked).toEqual(["Top 5 product categories by items sold"]);
  });

  it("shows no buttons for a numbers answer", () => {
    const numbers: FinishedAnswer = { ...BASE, route: "numbers", text: "Revenue: R$ 1.00.", how: ["x"] };
    const html = renderToStaticMarkup(<AnswerView answer={numbers} onAsk={() => {}} />);
    expect(html).not.toContain("suggestion");
    expect(html).toContain("How I got this");
  });
});
