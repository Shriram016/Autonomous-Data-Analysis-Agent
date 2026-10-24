"""The worker's job: answer one question (§0 M1.4–M1.5).

A worker process takes a slip from the queue and runs answer_question:

1. mark the question's row `running` (Postgres)
2. run the M1.3 agent graph, publishing a progress event before each node (Redis Stream)
3. save the answer and its usage in the row, then publish `done`

The answer lives in Postgres, so the Celery result is only a small status. The context is
loaded when each worker process starts (warm-up), so the first user does not wait for it.
"""

from typing import Any
from uuid import UUID

from celery.app import trace
from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_process_init

from adaa.agent.context import get_context
from adaa.agent.graph import ask
from adaa.agent.state import NO_USAGE, FinishedAnswer
from adaa.conversation import questions
from adaa.worker import events
from adaa.worker.celery_app import app
from adaa.worker.events import ProgressEvent

TIMEOUT_TEXT = "That question took too long. Try a narrower time range or fewer breakdowns."
CRASH_TEXT = "Something went wrong while answering. Please try again."

# What the user sees while each graph node runs.
STEP_TEXT = {
    "understand": "Understanding the question…",
    "query": "Running the query…",
    "answer": "Writing the answer…",
}

# Celery's "succeeded" log line prints the whole return value. Our logging rule is names and
# counts only, never question or answer text (the same rule as llm.complete), so keep the
# job name, id and run time, and drop the value.
trace.LOG_SUCCESS = "Task %(name)s[%(id)s] succeeded in %(runtime)ss"


@worker_process_init.connect
def warm_up(**_: Any) -> None:
    """Load the context once, as soon as a worker process starts."""
    get_context()


@app.task(name="adaa.answer_question")
def answer_question(question_id: str, question: str) -> dict[str, Any]:
    qid = UUID(question_id)
    context = get_context()
    questions.mark_running(qid)

    def on_step(node: str) -> None:
        events.publish(qid, ProgressEvent(kind="step", text=STEP_TEXT[node]))

    try:
        answer = ask(question, context, on_step=on_step)
    except SoftTimeLimitExceeded:  # task_soft_time_limit reached: answer, don't just die
        answer = FinishedAnswer(
            question=question,
            status="failed",
            text=TIMEOUT_TEXT,
            error_kind="job_timeout",
            versions=context.versions,
            usage=NO_USAGE,  # calls already made are in the usage log lines
        )
    except Exception:  # a bug: no answer at all. Record it, tell the UI, let Celery log it.
        questions.mark_failed(qid)
        events.publish(qid, ProgressEvent(kind="failed", text=CRASH_TEXT))
        raise

    questions.save_answer(qid, answer)
    events.publish(qid, ProgressEvent(kind="done"))
    return {"question_id": question_id, "status": answer.status}  # the answer is in Postgres
