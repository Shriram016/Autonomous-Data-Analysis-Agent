"""The Celery app: the job queue between the API and the workers (§0 M1.4, Celery locked).

Redis holds the job slips (the broker); workers take one slip at a time and run the agent.
Celery has hundreds of settings; only the few below are set, each for a reason. Crash
safety is OFF in Celery by default, so the first two settings matter most: together they
keep a question on the queue until a worker has really finished it.
"""

from celery import Celery

from adaa.settings import get_settings

SLOWEST_QUESTION_S = 100  # 2 agent attempts + answer at 30 s each + a 5 s query, rounded up

app = Celery("adaa", broker=get_settings().redis_url)
app.conf.update(
    # --- Crash safety (off in Celery by default) ---
    task_acks_late=True,  # remove the slip from Redis only AFTER the job finishes
    task_reject_on_worker_lost=True,  # worker died mid-job? put the slip back on the queue
    broker_transport_options={  # settings for the Redis connection
        # an unfinished slip goes back to the queue after 300 s; must be longer than
        # the slowest question, or a slow job is given to a second worker and runs twice
        "visibility_timeout": 3 * SLOWEST_QUESTION_S,
    },
    # --- How much work a worker takes ---
    worker_prefetch_multiplier=1,  # take 1 slip at a time, not a pile it may never reach
    # --- Stuck jobs ---
    task_soft_time_limit=150,  # after 150 s: raise an error the task can catch and handle
    task_time_limit=180,  # after 180 s: kill the job (the soft limit gave it 30 s to stop)
    # --- Message format (security) ---
    task_serializer="json",  # job slips are written as JSON
    result_serializer="json",  # results are written as JSON
    accept_content=["json"],  # refuse anything else: pickle can run code from a message
)
