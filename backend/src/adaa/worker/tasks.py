"""The worker's job: answer one question (§0 M1.4).

A worker process takes a slip from the queue and runs answer_question, which runs the M1.3
agent graph. The result goes back as JSON (Celery's message format), so it is a plain dict
made from the FinishedAnswer model.

The context is loaded when each worker process starts (warm-up), so the first user does not
wait for the catalogue and data-date queries.
"""

from typing import Any

from celery.app import trace
from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_process_init

from adaa.agent.context import get_context
from adaa.agent.graph import ask
from adaa.agent.state import NO_USAGE, FinishedAnswer
from adaa.worker.celery_app import app

TIMEOUT_TEXT = "That question took too long. Try a narrower time range or fewer breakdowns."

# Celery's "succeeded" log line prints the whole return value: the question, the answer and
# the table. Our logging rule is names and counts only, never question or answer text (the
# same rule as llm.complete), so keep the job name, id and run time, and drop the value.
trace.LOG_SUCCESS = "Task %(name)s[%(id)s] succeeded in %(runtime)ss"


@worker_process_init.connect
def warm_up(**_: Any) -> None:
    """Load the context once, as soon as a worker process starts."""
    get_context()


@app.task(name="adaa.answer_question")
def answer_question(question: str) -> dict[str, Any]:
    context = get_context()
    try:
        answer = ask(question, context)
    except SoftTimeLimitExceeded:  # task_soft_time_limit reached: answer, don't just die
        answer = FinishedAnswer(
            question=question,
            status="failed",
            text=TIMEOUT_TEXT,
            error_kind="job_timeout",
            versions=context.versions,
            usage=NO_USAGE,  # calls already made are in the usage log lines
        )
    return answer.model_dump(mode="json")
