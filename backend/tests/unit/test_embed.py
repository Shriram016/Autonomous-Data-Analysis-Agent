"""The embed checks, with a fake embedder: no model download, no cost."""

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from adaa.ingestion.embed import DIMS, QUERY_INSTRUCTION, EmbedError, embed_question, embed_reviews


@dataclass
class FakeEmbedder:
    vector: list[float] = field(default_factory=lambda: [0.1] * DIMS)
    seen: list[str] = field(default_factory=list)

    def embed(self, documents: list[str]) -> list[Sequence[float]]:
        self.seen += documents
        return [self.vector for _ in documents]


def test_reviews_get_one_vector_each_and_no_instruction() -> None:
    fake = FakeEmbedder()
    vectors = embed_reviews(["arrived late", "great product"], fake)
    assert len(vectors) == 2 and all(len(v) == DIMS for v in vectors)
    assert fake.seen == ["arrived late", "great product"]


def test_a_question_gets_the_search_instruction() -> None:
    fake = FakeEmbedder()
    assert len(embed_question("Why do customers complain?", fake)) == DIMS
    assert fake.seen == [QUERY_INSTRUCTION + "Why do customers complain?"]


@pytest.mark.parametrize(
    "vector",
    [[0.1] * (DIMS - 1), [0.1] * (DIMS - 1) + [float("nan")], [float("inf")] * DIMS],
)
def test_a_bad_vector_stops_the_group(vector: list[float]) -> None:
    with pytest.raises(EmbedError):
        embed_reviews(["arrived late"], FakeEmbedder(vector))
