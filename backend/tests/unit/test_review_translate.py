"""The translate answer: the English text only (§0 M3). No LLM, no database."""

import json

import pytest
from pydantic import ValidationError

from adaa.ingestion.review_translate import (
    ReviewTranslation,
    check_translation,
    load_review_prompt,
    translate_one,
)
from adaa.ingestion.reviews import says_something
from adaa.llm.adapters.fake import FakeAdapter


def test_a_good_answer_is_accepted() -> None:
    answer = ReviewTranslation.model_validate({"text_en": "Arrived broken"})
    assert answer.text_en == "Arrived broken"


@pytest.mark.parametrize(
    "answer",
    [
        {},  # the translation is required
        {"text_en": "Arrived broken", "tone": "negative"},  # tags were dropped: no extra fields
    ],
)
def test_a_bad_answer_is_rejected(answer: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ReviewTranslation.model_validate(answer)


def test_the_prompt_asks_for_the_translation_only() -> None:
    prompt = load_review_prompt()
    assert prompt.version == "0.4.0" and "{{" not in prompt.text
    assert "text_en" in prompt.text and "not_mentioned" not in prompt.text


def test_translate_one_sends_the_prompt_and_the_review_and_retries_a_bad_answer() -> None:
    bad = json.dumps({"text_en": "Arrived broken", "tone": "negative"})  # an extra field
    fake = FakeAdapter([bad, json.dumps({"text_en": "Terrible. It arrived broken"})])
    prompt = load_review_prompt()
    result = translate_one("Péssimo. Chegou quebrado", prompt, adapter=fake)
    assert result.output.text_en == "Terrible. It arrived broken" and len(fake.calls) == 2
    first = fake.calls[0]
    assert [m.content for m in first.messages] == [prompt.text, "Péssimo. Chegou quebrado"]
    assert first.job.model_name == "claude-haiku-5-5" and first.job.settings.cache == "5m"


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
    problems = check_translation(text_pt, ReviewTranslation(text_en=text_en))
    if problem is None:
        assert problems == []
    else:
        assert any(p.startswith(problem) for p in problems), problems


@pytest.mark.parametrize(
    ("text", "kept"),
    [(". .", False), (".", False), ("!!!", False), ("👍", True), ("bom", True), ("10", True)],
)
def test_plain_punctuation_says_nothing(text: str, kept: bool) -> None:
    assert says_something(text) is kept
