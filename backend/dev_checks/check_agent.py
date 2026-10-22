"""M1.3 check: 5 English questions through the whole agent graph, real Claude + real Postgres.

Costs money (~$0.003 for the run). Runs only by hand, never in tests or hooks. Needs Docker
running and ANTHROPIC_API_KEY in .env. Checks the flow and a few numbers we already know;
full scoring of many questions is the M1.7 eval harness.

Run from backend/:  uv run python dev_checks/check_agent.py
"""

import logging
import sys
from collections.abc import Callable

from adaa.agent.context import get_context
from adaa.agent.graph import ask
from adaa.agent.state import FinishedAnswer

Check = Callable[[FinishedAnswer], bool]

CASES: list[tuple[str, str, Check]] = [
    (
        "What was the total revenue?",
        "total = R$ 13,221,498.11 (delivered, the default)",
        lambda a: a.table is not None and a.table.rows == [["R$ 13,221,498.11"]],
    ),
    (
        "Revenue by customer state in 2017",
        "27 states, SP first",
        lambda a: (
            a.table is not None
            and len(a.table.rows) == 27
            and a.table.rows[0][0] == "SP (São Paulo)"
        ),
    ),
    (
        "Revenue for toy products",
        "the filter uses the real value toys",
        lambda a: "Filter: Product category = toys." in a.how,
    ),
    (
        "How many orders were canceled?",
        "461 canceled orders, not 0",
        lambda a: a.table is not None and a.table.rows == [["461"]],
    ),
    (
        "Revenue in Paris",
        "stops: Paris is not in the data",
        lambda a: a.status == "failed" and a.error_kind == "value_not_found",
    ),
]


def show(answer: FinishedAnswer) -> None:
    template = "  (template answer)" if answer.used_template else ""
    print(f"  status: {answer.status}{f' / {answer.error_kind}' if answer.error_kind else ''}")
    print(f"  answer: {answer.text}{template}")
    if answer.table:
        print(f"  table:  {' | '.join(answer.table.headers)}")
        for row in answer.table.rows[:3]:
            print(f"          {' | '.join(row)}")
        if len(answer.table.rows) > 3:
            print(f"          ... {len(answer.table.rows)} rows in total")
    for line in answer.how:
        print(f"  how:    {line}")
    u = answer.usage
    print(f"  cost:   ${u.cost_usd:.6f}  ({u.input_tokens:,} in, {u.output_tokens:,} out)")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # São Paulo on Windows
    logging.basicConfig(level=logging.WARNING, format="  log: %(message)s")
    logging.getLogger("adaa.llm").setLevel(logging.INFO)  # one usage line per LLM call
    context = get_context()
    print(f"Versions: {context.versions.model_dump()}")

    passed, total_cost = 0, 0.0
    for question, expected, check in CASES:
        print(f"\n=== {question}")
        answer = ask(question, context)
        show(answer)
        ok = check(answer)
        passed += ok
        total_cost += answer.usage.cost_usd
        print(f"  CHECK {'PASS' if ok else 'FAIL'}: {expected}")

    print(f"\n{passed} of {len(CASES)} checks passed. Total cost: ${total_cost:.6f}")


if __name__ == "__main__":
    main()
