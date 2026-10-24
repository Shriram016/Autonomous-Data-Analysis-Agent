"""Submit a question and fetch it by id (§0 M1.4–M1.5). The API calls these two functions.

submit() creates the question's row in Postgres FIRST, then queues the job with the question
id as the Celery job id, so there is one id for everything. get_result() reads the row from
Postgres with the owner check. Because the row exists from the start, an unknown id is really
unknown: this closes the M1.4 gap where Celery showed unknown, expired and queued jobs all
as PENDING.
"""

from uuid import UUID

from adaa.conversation import questions
from adaa.conversation.questions import QuestionRecord
from adaa.worker.tasks import answer_question


def submit(owner: str, question: str) -> UUID:
    """Create the question's row, queue the job; return the question id at once."""
    question_id = questions.create_question(owner, question)
    answer_question.apply_async(args=(str(question_id), question), task_id=str(question_id))
    return question_id


def get_result(question_id: UUID, owner: str) -> QuestionRecord | None:
    """The question's row (state, answer, usage), or None if unknown or someone else's."""
    return questions.get_question(question_id, owner)
