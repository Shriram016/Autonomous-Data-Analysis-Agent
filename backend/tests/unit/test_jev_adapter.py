"""The Jev adapter against a fake HTTP server (httpx.MockTransport): no key, no cost."""

import json
from typing import Any

import httpx
import pytest

from adaa.llm.adapters import jev_adapter
from adaa.llm.adapters.jev_adapter import ENDPOINT, JevAdapter, MissingKeyError
from adaa.llm.config import load
from adaa.llm.types import LlmOutputError, LlmUnavailableError

CRITERIA = {"numbers": "a data question", "off_topic": "not about the data"}
JOB = load().job_settings("route_jev")


def answer(choice: str = "numbers", confidence: float = 0.92) -> dict[str, Any]:
    """The documented reply shape (OpenRouter's page, 2026-10-26)."""
    return {
        "model": "typesafe/jev-1.14",
        "answers": {
            "choice": {
                "choice": choice,
                "probabilities": {"numbers": confidence, "off_topic": 1 - confidence},
                "confidence": confidence,
            }
        },
        "usage": {"input_tokens": 300, "output_tokens": 0, "cost": 0.0000126},
    }


def adapter(handler: Any) -> JevAdapter:
    return JevAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture(autouse=True)
def fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jev_adapter, "read_secret", lambda name: "test-key")


def test_sends_one_choice_question_and_reads_the_answer() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=answer())

    reply = adapter(handler).choose("Revenue in 2017", "Pick the route.", CRITERIA, JOB)
    assert json.loads(reply.text) == {"choice": "numbers", "confidence": 0.92}
    assert reply.usage.input_tokens == 300 and reply.usage.cost_usd == pytest.approx(0.0000126)

    request = sent[0]
    assert str(request.url) == ENDPOINT
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "typesafe/jev-1.14" and body["state"] == "Revenue in 2017"
    question = body["questions"]["choice"]
    assert question == {"type": "choice", "instructions": "Pick the route.", "criteria": CRITERIA}


def test_missing_key_fails_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jev_adapter, "read_secret", lambda name: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request without a key")

    with pytest.raises(MissingKeyError, match="OPENROUTER_API_KEY"):
        adapter(handler).choose("q", "i", CRITERIA, JOB)


@pytest.mark.parametrize("status", [401, 429, 500, 400])
def test_an_error_status_means_unavailable(status: int) -> None:
    with pytest.raises(LlmUnavailableError, match=f"({status})"):
        adapter(lambda r: httpx.Response(status)).choose("q", "i", CRITERIA, JOB)


def test_a_timeout_means_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LlmUnavailableError, match="too long"):
        adapter(handler).choose("q", "i", CRITERIA, JOB)


@pytest.mark.parametrize(
    "reply",
    [
        {"answers": {}},  # the format changed
        answer(choice="poem"),  # an option we never offered
    ],
)
def test_a_wrong_reply_is_an_output_error(reply: dict[str, Any]) -> None:
    with pytest.raises(LlmOutputError):
        adapter(lambda r: httpx.Response(200, json=reply)).choose("q", "i", CRITERIA, JOB)
