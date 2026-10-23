"""M1.4 check: questions through the real queue and the Docker worker, plus a crash test.

This script plays the API's part: it submits jobs into Redis and polls their state. The
Celery worker in Docker picks them up by itself. Costs money (~$0.002). Runs only by hand.
Needs the 3 containers healthy (docker compose ps) and ANTHROPIC_API_KEY in .env.

Crash test: while a job is running, every worker process inside the container is killed.
With task_acks_late + task_reject_on_worker_lost, Celery puts the job back on the queue,
new worker processes start, and the job still ends "done".

Run from backend/:  uv run python dev_checks/check_worker.py
"""

import subprocess
import sys
import time

from adaa.worker.jobs import JobStatus, get_result, submit

CONTAINER = "adaa-worker-1"
WAIT_S = 120

# Kill every child of PID 1 (the Celery main process) in the container: the worker
# processes that run tasks. Uses only /proc, grep and kill, which the slim image has.
KILL_WORKERS = (
    'for p in /proc/[0-9]*; do grep -q "^PPid:[[:space:]]*1$" "$p/status" 2>/dev/null '
    '&& kill -9 "${p#/proc/}"; done'
)


def follow(job_id: str, on_running: object = None) -> tuple[JobStatus, list[str]]:
    """Poll once a second; return the last status and every state seen, in order."""
    seen: list[str] = []
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        status = get_result(job_id)
        if not seen or seen[-1] != status.state:
            seen.append(status.state)
            print(f"  state: {status.state}")
            if status.state == "running" and callable(on_running):
                on_running()
        if status.state in ("done", "failed"):
            return status, seen
        time.sleep(1)
    return status, seen


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
    for question, name, expect in [
        (
            "What was the total revenue?",
            "answered, R$ 13,221,498.11",
            lambda s: s.answer.status == "answered" and "R$ 13,221,498.11" in s.answer.text,
        ),
        (
            "Revenue in Paris",
            "done, with the plain value_not_found message",
            lambda s: s.answer.status == "failed" and s.answer.error_kind == "value_not_found",
        ),
    ]:
        job_id = submit(question)
        print(f"\n{question}\n  job: {job_id}")
        status, seen = follow(job_id)
        if status.answer:
            print(f"  answer: {status.answer.text}  (${status.answer.usage.cost_usd:.6f})")
        results.append(
            check(name, status.state == "done" and status.answer is not None and expect(status))
        )

    print("\n=== Part 2: crash test")
    question = "Revenue by customer state in 2017"
    job_id = submit(question)
    print(f"{question}\n  job: {job_id}")
    status, seen = follow(job_id, on_running=kill_workers)
    if status.answer:
        print(f"  answer: {status.answer.text}")
    results.append(check("the job survived the crash and ended done", status.state == "done"))

    print(f"\n{sum(results)} of {len(results)} checks passed.")


if __name__ == "__main__":
    main()
