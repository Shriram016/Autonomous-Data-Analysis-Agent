"""The real bge-small-en-v1.5 model (downloads 67 MB into data/models/ on the first run)."""

import math

import pytest

from adaa.ingestion.embed import embed_question, embed_reviews

pytestmark = pytest.mark.integration


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def test_similar_meanings_are_nearer() -> None:
    late, slow, great = embed_reviews(
        ["arrived late", "the delivery took too long", "great product"]
    )
    assert cosine(late, slow) > cosine(late, great)


def test_a_question_finds_the_matching_review() -> None:
    question = embed_question("Which customers complain about late delivery?")
    late, great = embed_reviews(["My order came two weeks after the date", "Lovely colour"])
    assert cosine(question, late) > cosine(question, great)
