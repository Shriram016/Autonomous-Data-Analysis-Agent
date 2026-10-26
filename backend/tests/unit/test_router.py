"""The router's order and fallbacks, with a fake Jev server and the fake chat model."""

import json
import logging
from datetime import date
from typing import Any

import httpx
import pytest

from adaa.agent.router import (
    ROUTES,
    RouteDecision,
    RouterTexts,
    build_router_texts,
    route_question,
)
from adaa.llm.adapters import jev_adapter
from adaa.llm.adapters.fake import FakeAdapter
from adaa.llm.adapters.jev_adapter import JevAdapter
from adaa.llm.config import LlmConfig, Router, load
from adaa.llm.types import LlmUnavailableError
from adaa.semantic_layer.definitions import load as load_layer

TEXTS = build_router_texts(load_layer(), date(2018, 8, 31))


def jev_says(choice: str, confidence: float = 0.9) -> JevAdapter:
    body = {"answers": {"choice": {"choice": choice, "confidence": confidence}}, "usage": {}}
    return JevAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    )


def jev_down() -> JevAdapter:
    return JevAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    )


def haiku_says(*replies: str | Exception) -> FakeAdapter:
    return FakeAdapter(list(replies))


def route(text: str) -> str:
    return json.dumps({"route": text})


def with_order(*jobs: str) -> LlmConfig:
    return load().model_copy(update={"router": Router(order=list(jobs))})


@pytest.fixture(autouse=True)
def fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jev_adapter, "read_secret", lambda name: "test-key")


def test_jev_answers_first_with_a_confidence() -> None:
    haiku = haiku_says()
    decision = route_question(
        "Revenue in 2017", TEXTS, jev=jev_says("numbers", 0.97), adapter=haiku
    )
    assert decision.route == "numbers" and decision.confidence == 0.97
    assert decision.source == "route_jev"
    assert haiku.calls == []  # the fallback was not needed


def test_jev_down_falls_back_to_haiku(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="adaa.agent")
    decision = route_question(
        "Best products?", TEXTS, jev=jev_down(), adapter=haiku_says(route("clarify"))
    )
    assert decision == RouteDecision(
        route="clarify", source="route_haiku", usage=decision.usage
    )  # no confidence from Haiku
    assert "router_fallback from=route_jev to=route_haiku reason=LlmUnavailableError" in caplog.text


def test_missing_jev_key_falls_back_with_its_reason(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(jev_adapter, "read_secret", lambda name: None)
    caplog.set_level(logging.WARNING, logger="adaa.agent")
    decision = route_question(
        "q", TEXTS, jev=jev_says("numbers"), adapter=haiku_says(route("refuse"))
    )
    assert decision.route == "refuse"
    assert "reason=MissingKeyError" in caplog.text


def test_every_option_fails_means_numbers(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="adaa.agent")
    haiku = haiku_says(LlmUnavailableError("down"))
    decision = route_question("q", TEXTS, jev=jev_down(), adapter=haiku)
    assert decision == RouteDecision(route="numbers", source="default")
    assert "router_failed tried=2 route=numbers" in caplog.text


def test_a_bad_haiku_reply_counts_as_a_failure() -> None:
    decision = route_question("q", TEXTS, jev=jev_down(), adapter=haiku_says(route("poem")))
    assert decision.source == "default"  # "poem" is not a route; no retry (max_attempts 1)


def test_one_config_line_makes_haiku_the_primary() -> None:
    haiku_first = with_order("route_haiku", "route_jev")
    decision = route_question(
        "q",
        TEXTS,
        config=haiku_first,
        jev=jev_says("off_topic"),
        adapter=haiku_says(route("metadata")),
    )
    assert decision.source == "route_haiku" and decision.route == "metadata"


def test_haiku_only_never_calls_jev() -> None:
    def no_call(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Jev is not in the order")

    jev = JevAdapter(client=httpx.Client(transport=httpx.MockTransport(no_call)))
    decision = route_question(
        "q", TEXTS, config=with_order("route_haiku"), jev=jev, adapter=haiku_says(route("numbers"))
    )
    assert decision.source == "route_haiku"


def test_both_models_get_the_same_route_descriptions() -> None:
    sent: list[dict[str, Any]] = []

    def capture(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(503)

    haiku = haiku_says(route("numbers"))
    jev = JevAdapter(client=httpx.Client(transport=httpx.MockTransport(capture)))
    route_question("q", TEXTS, jev=jev, adapter=haiku)
    assert sent[0]["questions"]["choice"]["criteria"] == ROUTES  # Jev's options
    system = haiku.calls[0].messages[0].content
    assert all(text in system for text in ROUTES.values())  # inside Haiku's prompt


def test_router_texts_come_from_the_semantic_layer() -> None:
    texts: RouterTexts = TEXTS
    assert texts.prompt.version == "0.1.0" and "{{" not in texts.prompt.text
    for words in ("cancellation_rate", "quarter", "best customers", "2018-08-31"):
        assert words in texts.prompt.text and words in texts.instructions
