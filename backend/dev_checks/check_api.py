"""M1.5 check: the whole service through the API, like the UI will use it.

Talks only to the API (http://127.0.0.1:8000): submit, watch the SSE stream live, read the
saved row. Costs money (~$0.001, 3 LLM calls). Runs only by hand. Needs the containers healthy
(api, worker, postgres, redis) and ANTHROPIC_API_KEY in .env.

Run from backend/:  uv run python dev_checks/check_api.py
"""

import json
import sys
import time
import uuid
from typing import Any

import httpx

API = "http://127.0.0.1:8000"


def check(name: str, ok: bool) -> bool:
    print(f"  CHECK {'PASS' if ok else 'FAIL'}: {name}")
    return ok


def ask(client: httpx.Client, question: str) -> tuple[str, dict[str, Any]]:
    """Submit, print the stream as it arrives; return the last event's name and data."""
    started = time.monotonic()
    reply = client.post(f"{API}/questions", json={"question": question})
    question_id = reply.json()["id"]
    print(f"\n=== {question}\n  POST /questions → {reply.status_code}, id {question_id}")

    event: str = ""
    data: dict[str, Any] = {}
    with client.stream("GET", f"{API}/questions/{question_id}/events", timeout=200) as stream:
        name = ""
        for line in stream.iter_lines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                event, data = name, json.loads(line.removeprefix("data: "))
                at = f"{time.monotonic() - started:5.1f}s"
                shown = data.get("text") or (data.get("answer") or {}).get("text")
                print(f"  {at}  {name}: {shown}")

    row = client.get(f"{API}/questions/{question_id}").json()
    print(
        f"  row: state {row['state']}, cost ${row['cost_usd']}, "
        f"wait {row['wait_seconds']} s, total {row['total_seconds']} s"
    )
    return event, data


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    results: list[bool] = []
    with httpx.Client() as client:
        event, data = ask(client, "Revenue by customer state in 2017")
        answer = data.get("answer") or {}
        results.append(check("streamed steps, then done with the answer", event == "done"))
        results.append(
            check(
                "SP first in the table",
                answer.get("table", {}).get("rows", [[""]])[0][0] == "SP (São Paulo)",
            )
        )

        event, data = ask(client, "Revenue in Paris")
        answer = data.get("answer") or {}
        results.append(
            check(
                "done with the plain value_not_found message",
                answer.get("error_kind") == "value_not_found",
            )
        )

        print("\n=== Free checks (no LLM call)")
        missing = client.get(f"{API}/questions/{uuid.uuid4()}")
        results.append(
            check(f"a random id → 404 (got {missing.status_code})", missing.status_code == 404)
        )
        long = client.post(f"{API}/questions", json={"question": "x" * 501})
        results.append(
            check(
                f"a 501-character question → 422 (got {long.status_code})", long.status_code == 422
            )
        )

    print(f"\n{sum(results)} of {len(results)} checks passed.")


if __name__ == "__main__":
    main()
