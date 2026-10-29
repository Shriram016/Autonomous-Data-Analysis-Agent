"""The translate + tag answer: tag list v1 (§0 M3). No LLM, no database."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from adaa.ingestion.review_tags import (
    MEANINGS,
    ReviewTags,
    check_meanings,
    check_translation,
    load_review_prompt,
    tag_one,
)
from adaa.llm.adapters.fake import FakeAdapter


def answer(**changes: Any) -> dict[str, Any]:
    good = {
        "text_en": "Terrible. The product arrived broken and 10 days late",
        "delivery": "late",
        "product": ["damaged_or_defective"],
        "service": ["not_mentioned"],
        "price": "not_mentioned",
        "tone": "negative",
    }
    return good | changes


def test_a_good_answer_is_accepted() -> None:
    tags = ReviewTags.model_validate(answer(product=["damaged_or_defective", "wrong_item"]))
    assert tags.delivery == "late" and tags.product == ["damaged_or_defective", "wrong_item"]


@pytest.mark.parametrize(
    "changes",
    [
        {"delivery": "slow"},  # not in the list
        {"tone": "not_mentioned"},  # every text has a tone
        {"product": []},  # say not_mentioned, never empty
        {"product": ["good", "not_mentioned"]},  # not_mentioned stands alone
        {"service": ["other", "other"]},  # no repeats
        {"category": "furniture"},  # no extra fields: category comes from products
    ],
)
def test_a_bad_answer_is_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ReviewTags.model_validate(answer(**changes))


def test_every_heading_is_required() -> None:
    incomplete = answer()
    del incomplete["price"]
    with pytest.raises(ValidationError):
        ReviewTags.model_validate(incomplete)


def test_every_value_has_a_meaning() -> None:
    check_meanings()  # raises if the prompt's meanings and the allowed values differ


def test_the_prompt_shows_every_value_once() -> None:
    prompt = load_review_prompt()
    assert prompt.version == "0.1.0" and "{{" not in prompt.text
    assert "`product` (a list):" in prompt.text and "`tone` (one value):" in prompt.text
    for values in MEANINGS.values():
        for value in values:
            assert f"- `{value}`:" in prompt.text


def test_tag_one_sends_the_prompt_and_the_review_and_retries_a_bad_answer() -> None:
    bad = json.dumps(answer(product=["good", "not_mentioned"]))  # not_mentioned not alone
    fake = FakeAdapter([bad, json.dumps(answer())])
    prompt = load_review_prompt()
    result = tag_one("Péssimo. Chegou quebrado e atrasou 10 dias", prompt, adapter=fake)
    assert result.output.delivery == "late" and len(fake.calls) == 2  # retried once
    first = fake.calls[0]
    assert [m.content for m in first.messages] == [
        prompt.text,
        "Péssimo. Chegou quebrado e atrasou 10 dias",
    ]
    assert first.job.model_name == "claude-haiku-5-5" and first.job.settings.cache == "5m"


def tagged(text_en: str) -> ReviewTags:
    return ReviewTags.model_validate(answer(text_en=text_en))


@pytest.mark.parametrize(
    ("text_pt", "text_en", "problem"),
    [
        ("Chegou quebrado e atrasou", "Arrived broken and late", None),
        ("bom", "good", None),  # too short to compare lengths
        ("Comprei na loja lannister", "I bought from the lannister store", None),  # a name
        ("Chegou quebrado e atrasou", "   ", "empty translation"),
        ("Produto não chegou ainda", "Produto não chegou ainda", "still Portuguese"),
        ("O produto chegou quebrado e atrasou dez dias", "Broken", "odd length"),
        ("Produto chegou quebrado", "The product arrived broken. " * 6, "odd length"),
    ],
)
def test_check_translation(text_pt: str, text_en: str, problem: str | None) -> None:
    problems = check_translation(text_pt, tagged(text_en))
    if problem is None:
        assert problems == []
    else:
        assert any(p.startswith(problem) for p in problems), problems
