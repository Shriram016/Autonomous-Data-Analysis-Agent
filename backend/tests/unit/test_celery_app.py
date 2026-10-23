from adaa.settings import get_settings
from adaa.worker.celery_app import SLOWEST_QUESTION_S, app


def test_broker_is_our_redis() -> None:
    assert app.conf.broker_url == get_settings().redis_url


def test_crash_safety_is_on() -> None:
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True


def test_timeouts_are_longer_than_the_slowest_question() -> None:
    visibility = app.conf.broker_transport_options["visibility_timeout"]
    assert visibility == 300 and visibility > app.conf.task_time_limit > SLOWEST_QUESTION_S
    assert app.conf.task_soft_time_limit < app.conf.task_time_limit


def test_one_job_at_a_time_and_json_only() -> None:
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.accept_content == ["json"] and app.conf.task_serializer == "json"
