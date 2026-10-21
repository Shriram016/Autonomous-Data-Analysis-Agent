"""M1.2 check: 3 English questions → Claude Haiku 5.5 → checked forms → SQL, printed.

The FIRST check that costs money (~$0.001 for the run). It runs only by hand, never in
tests or hooks. Needs ANTHROPIC_API_KEY in .env. No database query runs: each form only
goes through the compiler, to prove it makes valid SQL.

The prompt here is a short test prompt (the valid names only), not the M1.3 agent prompt.

Run from backend/:  uv run python dev_checks/check_llm.py
"""

import json
import logging

from adaa.llm.adapters.base import Message
from adaa.llm.complete import complete
from adaa.llm.types import LlmError, Usage
from adaa.semantic_layer.compiler import CompileError, compile_request
from adaa.semantic_layer.definitions import SemanticLayer, load
from adaa.semantic_layer.request import StructuredRequest

QUESTIONS = [
    "What was the total revenue?",
    "Revenue by customer state in 2017",
    "Top 5 product categories by revenue",
]


def test_prompt(layer: SemanticLayer) -> str:
    metrics = "\n".join(f"- {name}: {m.description}" for name, m in layer.metrics.items())
    dimensions = "\n".join(f"- {name}: {d.label}" for name, d in layer.dimensions.items())
    return (
        "You turn a business question about an e-commerce store into a JSON request form.\n"
        "Use only these metric names:\n"
        f"{metrics}\n"
        "Use only these dimension names:\n"
        f"{dimensions}\n"
        "Orders run from 2016-09 to 2018-10. Leave out any field the question does not need."
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="  log: %(message)s")
    layer = load()
    system = Message(role="system", content=test_prompt(layer))
    total: Usage | None = None

    for question in QUESTIONS:
        print(f"\n=== {question}")
        try:
            result = complete(
                "agent", [system, Message(role="user", content=question)], StructuredRequest
            )
        except LlmError as e:
            print(f"  FAILED: {e}")
            continue
        form = result.output.model_dump(exclude_defaults=True)
        u = result.usage
        print(f"  form: {json.dumps(form, default=str)}")
        print(
            f"  attempts={result.attempts}  tokens in={u.input_tokens:,} out={u.output_tokens:,}"
            f" thinking={u.thinking_tokens:,}  cost=${u.cost_usd:.6f}  {result.seconds:.1f}s"
        )
        try:
            sql = compile_request(result.output, layer).sql
            print("  sql:  " + "\n        ".join(sql.splitlines()))
        except CompileError as e:
            print(f"  compiler refused: {e}")
        total = u if total is None else total + u

    if total:
        tokens = f"{total.input_tokens:,} in, {total.output_tokens:,} out"
        print(f"\nTotal: {tokens}, ${total.cost_usd:.6f}")


if __name__ == "__main__":
    main()
