"""Text → 384-number vector with bge-small-en-v1.5, run locally by fastembed (§0 M3, 2026-10-28).

Reviews are embedded as they are. A question gets BGE's search instruction in front: the
model was trained that way for short questions against longer passages. fastembed does not
add it for this model (checked 2026-10-29), so we add it here, where it is visible and tested.

The model (67 MB) downloads once into data/models/ and is loaded once per process.
"""

import math
from collections.abc import Iterable
from functools import cache
from typing import Any, Protocol

from fastembed import TextEmbedding

from adaa.settings import REPO_ROOT

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
DIMS = 384  # must match the vector(384) column in business.review_vectors
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
MODELS_DIR = REPO_ROOT / "data" / "models"


class EmbedError(Exception):
    """A vector is the wrong size or holds a number that is not real: nothing is written."""


class Embedder(Protocol):
    """What we use from fastembed's TextEmbedding; tests pass a fake."""

    def embed(self, documents: list[str]) -> Iterable[Any]: ...  # numpy arrays from fastembed


@cache
def get_embedder() -> Embedder:
    return TextEmbedding(EMBED_MODEL, cache_dir=str(MODELS_DIR))


def checked(vectors: Iterable[Any], expected: int) -> list[list[float]]:
    out = [[float(n) for n in v] for v in vectors]
    if len(out) != expected:
        raise EmbedError(f"got {len(out)} vectors for {expected} texts")
    for i, v in enumerate(out):
        if len(v) != DIMS:
            raise EmbedError(f"vector {i} has {len(v)} numbers, not {DIMS}")
        if not all(math.isfinite(n) for n in v):
            raise EmbedError(f"vector {i} holds a number that is not real")
    return out


def embed_reviews(texts: list[str], embedder: Embedder | None = None) -> list[list[float]]:
    """English review texts → one vector each, in the same order. No instruction in front."""
    return checked((embedder or get_embedder()).embed(texts), len(texts))


def embed_question(text: str, embedder: Embedder | None = None) -> list[float]:
    """A question → its vector, with BGE's search instruction in front (search time, later)."""
    return checked((embedder or get_embedder()).embed([QUERY_INSTRUCTION + text]), 1)[0]
