"""M1.4–M1.5 check: questions through the real queue and the Docker worker, plus a crash test.

This script plays the API's part: it submits questions (a Postgres row + a job in Redis) and
polls the row. The Celery worker in Docker picks the jobs up by itself and publishes progress
events, which are printed at the end. Costs money (~$0.002). Runs only by hand. Needs the
containers healthy (docker compose ps) and ANTHROPIC_API_KEY in .env.

Crash test: while a question is running, every worker process inside the container is killed.
With task_acks_late + task_reject_on_worker_lost, Celery puts the job back on the queue, new
worker processes start, and the question still ends "done".

Run from backend/:  uv run python dev_checks/check_worker.py
"""

import subprocess
import sys
import time
from collections.abc import Callable
from uuid import UUID

from adaa.conversation.questions import LOCAL_OWNER, QuestionRecord
from adaa.worker import events
from adaa.worker.jobs import get_result, submit

CONTAINER = "adaa-worker-1"
WAIT_S = 120

# Kill every child of PID 1 (the Celery main process) in the container: the worker
# processes that run tasks. Uses only /proc, grep and kill, which the slim image has.
KILL_WORKERS = (
    'for p in /proc/[0-9]*; do grep -q "^PPid:[[:space:]]*1$" "$p/status" 2>/dev/null '
    '&& kill -9 "${p#/proc/}"; done'
)


def follow(question_id: UUID, on_running: Callable[[], None] | None = None) -> QuestionRecord:
    """Poll the row once a second; print each state change; return the last row."""
    last_state = ""
    deadline = time.monotonic() + WAIT_S
    while True:
        record = get_result(question_id, LOCAL_OWNER)
        assert record is not None, "the row is created at submit"
        if record.state != last_state:
            last_state = record.state
            print(f"  state: {record.state}")
            if record.state == "running" and on_running:
                on_running()
        if record.state in ("done", "failed") or time.monotonic() > deadline:
            return record
        time.sleep(1)


def show(question_id: UUID, record: QuestionRecord) -> None:
    for _, event in events.read(question_id):
        print(f"  event: {event.kind}{f'  {event.text}' if event.text else ''}")
    if record.answer:
        print(f"  answer: {record.answer.text}")
    times = f"wait {record.wait_seconds} s, total {record.total_seconds} s"
    print(f"  row: cost ${record.cost_usd}, {times}")


def kill_workers() -> None:
    time.sleep(1)  # let the job get into the agent
    print("  >>> killing every worker process in the container")
    subprocess.run(["docker", "exec", CONTAINER, "sh", "-c", KILL_WORKERS], check=False)


def check(name: str, ok: bool) -> bool:
    print(f"  CHECK {'PASS' if ok else 'FAIL'}: {name}")
    return ok


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    results: list[bool] = []

    print("=== Part 1: normal path")
    cases: list[tuple[str, str, Callable[[QuestionRecord], bool]]] = [
        (
            "What was the total revenue?",
            "answered, R$ 13,221,498.11",
            lambda r: r.answer is not None and "R$ 13,221,498.11" in r.answer.text,
        ),
        (
            "Revenue in Paris",
            "done, with the plain value_not_found message",
            lambda r: r.answer is not None and r.answer.error_kind == "value_not_found",
        ),
    ]
    for question, name, expect in cases:
        question_id = submit(LOCAL_OWNER, question)
        print(f"\n{question}\n  id: {question_id}")
        record = follow(question_id)
        show(question_id, record)
        results.append(check(name, record.state == "done" and expect(record)))

    print("\n=== Part 2: crash test")
    question = "Revenue by customer state in 2017"
    question_id = submit(LOCAL_OWNER, question)
    print(f"{question}\n  id: {question_id}")
    record = follow(question_id, on_running=kill_workers)
    show(question_id, record)
    results.append(check("the question survived the crash and ended done", record.state == "done"))

    print(f"\n{sum(results)} of {len(results)} checks passed.")


if __name__ == "__main__":
    main()
