"""Submit a question and fetch its answer by job number (§0 M1.4, step 3).

The API (M1.5) calls these two functions. submit() returns at once with a job number; the
slow work happens in a worker. get_result() turns Celery's job states into four plain ones.
Finished answers wait in Redis for 1 day (the "pickup counter"); the permanent record goes
to Postgres in M1.5.

Two kinds of failure, kept apart:
- `done` with status "failed": the agent ran and gave a plain message ("Paris" not in data).
- `failed`: the job itself crashed (a bug, a killed process); there is no answer at all.
"""

from typing import Any, Literal

from celery.result import AsyncResult
from pydantic import BaseModel, ConfigDict

from adaa.agent.state import FinishedAnswer
from adaa.worker.celery_app import app
from adaa.worker.tasks import answer_question

JobState = Literal["waiting", "running", "done", "failed"]

# Celery state → our state. PENDING also means "unknown job number" or "result expired":
# Celery can't tell those apart from a job still in the queue.
STATES: dict[str, JobState] = {
    "PENDING": "waiting",
    "RETRY": "waiting",
    "STARTED": "running",
    "SUCCESS": "done",
    "FAILURE": "failed",
    "REVOKED": "failed",
}


class JobStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    state: JobState
    answer: FinishedAnswer | None = None  # only when state is "done"


def submit(question: str) -> str:
    """Put the question on the queue; return its job number at once."""
    return answer_question.delay(question).id


def get_result(job_id: str) -> JobStatus:
    result: AsyncResult[Any] = AsyncResult(job_id, app=app)
    state = STATES.get(result.state, "waiting")
    answer = FinishedAnswer.model_validate(result.result) if state == "done" else None
    return JobStatus(job_id=job_id, state=state, answer=answer)
