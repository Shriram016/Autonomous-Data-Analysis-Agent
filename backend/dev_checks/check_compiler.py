"""M1.1 check: 5 hand-written forms through compiler → runner, printed for a person to read.

The forms are written by hand here; from M1.3 the LLM fills them in from English questions.

Run from backend/:  uv run python dev_checks/check_compiler.py
"""

import json
from typing import Any

from adaa.semantic_layer.compiler import CompileError, compile_request
from adaa.semantic_layer.definitions import load
from adaa.semantic_layer.request import StructuredRequest
from adaa.semantic_layer.runner import run_query
from adaa.settings import get_settings

SAMPLES: list[tuple[str, dict[str, Any]]] = [
    ("What was our total revenue?", {"metric": "revenue"}),
    (
        "Top 5 states by revenue in 2017",
        {
            "metric": "revenue",
            "dimensions": ["customer_state"],
            "period": {"start": "2017-01-01", "end": "2017-12-31"},
            "limit": 5,
        },
    ),
    (
        "Late-delivery rate by month in 2018",
        {
            "metric": "late_delivery_rate",
            "dimensions": ["month"],
            "period": {"start": "2018-01-01", "end": "2018-08-31"},
            "sort": {"by": "month", "direction": "asc"},
        },
    ),
    (
        "Revenue for toys and books, by category",
        {
            "metric": "revenue",
            "dimensions": ["product_category"],
            "filters": [
                {
                    "dimension": "product_category",
                    "op": "in",
                    "values": ["toys", "books_general_interest"],
                }
            ],
        },
    ),
    ("Total paid by category", {"metric": "total_paid", "dimensions": ["product_category"]}),
]


def show(value: object) -> str:
    if isinstance(value, int | str):
        return f"{value:,}" if isinstance(value, int) else value
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m")
    return f"{float(value):,.4f}" if abs(float(value)) < 1 else f"{float(value):,.2f}"  # type: ignore[arg-type]


def main() -> None:
    layer = load()
    conninfo = get_settings().postgres_conninfo("query")
    for number, (question, form) in enumerate(SAMPLES, start=1):
        print(f"\n=== {number}. {question} ===")
        print(f"Form:   {json.dumps(form)}")
        try:
            compiled = compile_request(StructuredRequest.model_validate(form), layer)
        except CompileError as refusal:
            print(f"Refused: {refusal}")
            continue
        print("SQL:\n  " + compiled.sql.replace("\n", "\n  "))
        print("Values: " + ", ".join(f"{k}={v}" for k, v in compiled.params.items()))
        result = run_query(compiled, conninfo)
        print(f"Rows ({result.row_count}):")
        for row in result.rows[:12]:
            print("  " + "  ".join(f"{show(v):>16}" for v in row))
        if result.row_count > 12:
            print(f"  … {result.row_count - 12} more")
        print("How:")
        for line in result.explanation:
            print(f"  - {line}")
        print(f"Time:   {result.elapsed_ms} ms")
    print("\nM1.1 compiler check passed.")


if __name__ == "__main__":
    main()
